"""Explicit local database reset. Stop API and worker before invocation."""

import argparse

from alembic.config import Config

from alembic import command
from app.scripts.seed import seed


def main():
    parser = argparse.ArgumentParser(description="Destroy application data and restore demo seed.")
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        required=True,
        help="Confirm permanent deletion; API and worker must be stopped.",
    )
    parser.parse_args()
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    seed()
    print("Database reset complete.")


if __name__ == "__main__":
    main()
