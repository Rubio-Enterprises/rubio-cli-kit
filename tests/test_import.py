from rubio_cli_kit import _cli, _logging, _output, _paths


def test_distribution_ships_all_four_helper_modules() -> None:
    modules = (_cli, _logging, _output, _paths)

    assert all(module.__package__ == 'rubio_cli_kit' for module in modules)
