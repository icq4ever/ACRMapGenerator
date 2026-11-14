"""ACR Map Generator: build rally stages for Assetto Corsa Rally from open geodata."""


def main() -> None:
    from .cli import main as _main

    _main()
