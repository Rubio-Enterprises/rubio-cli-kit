"""Hermetic subprocess fixtures for CLI contract and consumer tests."""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")
DEFAULT_TIMEOUT_SECONDS = 30.0
SUPPORTED_HTTP_METHODS = frozenset({"GET", "POST"})


def _join(root: Path, parts: tuple[str, ...]) -> Path:
    path = root
    for part in parts:
        path /= part
    return path


@dataclass(frozen=True)
class FakePath:
    """A PATH-prepend directory for fake external binaries."""

    path: Path

    def executable(self, name: str, body: str) -> Path:
        script = self.path / name
        self.path.mkdir(parents=True, exist_ok=True)
        script.write_text(f"#!/bin/sh\n{body.rstrip()}\n")
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return script

    def recording_executable(
        self,
        name: str,
        argv_log: Path,
        *,
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> Path:
        lines = [f'printf "%s\\0" "$#" "$@" >> {shlex.quote(str(argv_log))}']
        if stdout:
            lines.append(f"printf %s {shlex.quote(stdout)}")
        if stderr:
            lines.append(f"printf %s {shlex.quote(stderr)} >&2")
        lines.append(f"exit {exit_code}")
        return self.executable(name, "\n".join(lines))


@dataclass
class CliSandbox:
    """A hermetic HOME/XDG/PATH environment for subprocess CLI tests."""

    home: Path
    scripts_dir: Path
    path_prepend: list[Path] = field(default_factory=list)
    env_extra: dict[str, str] = field(default_factory=dict)
    cleanup_callbacks: list[Callable[[], None]] = field(default_factory=list)

    def xdg_config_path(self, *parts: str) -> Path:
        return _join(self.home / ".config", parts)

    def xdg_data_path(self, *parts: str) -> Path:
        return _join(self.home / ".local" / "share", parts)

    def xdg_state_path(self, *parts: str) -> Path:
        return _join(self.home / ".local" / "state", parts)

    def xdg_cache_path(self, *parts: str) -> Path:
        return _join(self.home / ".cache", parts)

    def fake_path(self, dirname: str = "fake-bin") -> FakePath:
        fake = FakePath(self.home / dirname)
        if fake.path not in self.path_prepend:
            self.path_prepend.append(fake.path)
        return fake

    def fake_http_server(self) -> FakeHttpServer:
        server = FakeHttpServer()
        self.add_cleanup(server.close)
        return server

    def add_cleanup(self, callback: Callable[[], None]) -> None:
        self.cleanup_callbacks.append(callback)

    def close(self) -> None:
        errors: list[Exception] = []
        for callback in reversed(self.cleanup_callbacks):
            try:
                callback()
            except Exception as exc:
                errors.append(exc)
        self.cleanup_callbacks.clear()
        if errors:
            messages = "; ".join(str(error) for error in errors)
            raise RuntimeError(f"CliSandbox cleanup failed: {messages}")

    def environ(
        self,
        *,
        path_prepend: Sequence[Path] = (),
        env_extra: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        path = [
            *(str(item) for item in path_prepend),
            *(str(item) for item in self.path_prepend),
            str(self.scripts_dir),
            *SYSTEM_PATH,
        ]
        return {
            "HOME": str(self.home),
            "PATH": os.pathsep.join(path),
            "XDG_CONFIG_HOME": str(self.xdg_config_path()),
            "XDG_DATA_HOME": str(self.xdg_data_path()),
            "XDG_STATE_HOME": str(self.xdg_state_path()),
            "XDG_CACHE_HOME": str(self.xdg_cache_path()),
            "NO_COLOR": "1",
            **self.env_extra,
            **(env_extra or {}),
        }

    def run(
        self,
        command: str,
        *args: str,
        path_prepend: Sequence[Path] = (),
        env_extra: Mapping[str, str] | None = None,
        input_text: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [str(self.scripts_dir / command), *args],
            input=input_text,
            capture_output=True,
            text=True,
            env=self.environ(path_prepend=path_prepend, env_extra=env_extra),
            check=False,
            timeout=timeout,
        )


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str]


@dataclass(frozen=True)
class HttpRequest:
    method: str
    path: str
    body: bytes
    headers: Mapping[str, str]


class FakeHttpServer:
    """Local HTTP fake for commands that need transport-level tests."""

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], HttpResponse] = {}
        self._requests: list[HttpRequest] = []
        routes = self._routes
        requests = self._requests

        def handle(handler: BaseHTTPRequestHandler, method: str) -> None:
            length = int(handler.headers.get("Content-Length", "0") or "0")
            body = handler.rfile.read(length) if length else b""
            requests.append(HttpRequest(method, handler.path, body, dict(handler.headers.items())))
            response = routes.get((method, handler.path))
            if response is None:
                response = HttpResponse(404, b"not found", {})
            handler.send_response(response.status)
            for key, value in response.headers.items():
                handler.send_header(key, value)
            handler.send_header("Content-Length", str(len(response.body)))
            handler.end_headers()
            handler.wfile.write(response.body)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                handle(self, "GET")

            def do_POST(self) -> None:
                handle(self, "POST")

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def route(
        self,
        path: str,
        body: str | bytes,
        *,
        method: str = "GET",
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        normalized_method = method.upper()
        if normalized_method not in SUPPORTED_HTTP_METHODS:
            supported = ", ".join(sorted(SUPPORTED_HTTP_METHODS))
            raise ValueError(
                f"unsupported HTTP method {normalized_method!r}; expected one of: {supported}"
            )
        normalized = path if path.startswith("/") else f"/{path}"
        payload = body.encode() if isinstance(body, str) else body
        self._routes[(normalized_method, normalized)] = HttpResponse(status, payload, headers or {})
        return self.url(normalized)

    @property
    def requests(self) -> tuple[HttpRequest, ...]:
        return tuple(self._requests)

    def url(self, path: str = "/") -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        return f"http://127.0.0.1:{self._server.server_port}{normalized}"

    def close(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()
