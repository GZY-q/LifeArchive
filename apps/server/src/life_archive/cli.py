"""Local administration only: initialize an owner without exposing passwords in argv."""

import argparse
import getpass
import hmac
import sys

from sqlalchemy.exc import SQLAlchemyError

from life_archive.auth.service import OwnerSetupError, create_owner
from life_archive.db import get_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m life_archive.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    init_owner = commands.add_parser("init-owner", help="Create the sole owner; never overwrite")
    init_owner.add_argument("--username", required=True)
    init_owner.add_argument("--timezone", default="UTC")
    init_owner.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one password line from stdin for automation",
    )
    arguments = parser.parse_args(argv)

    try:
        if arguments.password_stdin:
            password = sys.stdin.read(1026).removesuffix("\n").removesuffix("\r")
            if "\n" in password or "\r" in password:
                raise OwnerSetupError("Password input must contain exactly one line")
        else:
            password = getpass.getpass("Owner password (at least 15 characters): ")
            confirmation = getpass.getpass("Confirm owner password: ")
            if not hmac.compare_digest(password.encode("utf-8"), confirmation.encode("utf-8")):
                raise OwnerSetupError("Passwords do not match; no changes were made")
        with get_session_factory()() as db:
            create_owner(db, arguments.username, password, arguments.timezone)
    except (OwnerSetupError, EOFError) as error:
        print(str(error) or "Password input ended unexpectedly", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Database unavailable or migrations missing; owner was not created", file=sys.stderr)
        return 1
    print("Owner created successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
