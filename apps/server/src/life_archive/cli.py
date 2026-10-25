"""Local administration: private owner initialization and read-only journal export."""

import argparse
import getpass
import hmac
import json
import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from life_archive.auth.service import OwnerSetupError, create_owner
from life_archive.db import get_engine, get_session_factory
from life_archive.journal.export import ExportError, export_journal


def _export(output: str, include_deleted: bool) -> int:
    try:
        result = export_journal(get_engine(), Path(output), include_deleted=include_deleted)
    except KeyboardInterrupt:
        reason, status = "Export interrupted", 130
    except FileExistsError:
        reason, status = "Output already exists; choose a new path", 1
    except ExportError as error:
        reason, status = str(error), 1
    except Exception:
        # SQL/OS/config errors can contain credentials or source data. The CLI
        # boundary intentionally prints a fixed message without a traceback.
        reason, status = "Export failed; check database, migrations and output access", 1
    else:
        print(
            json.dumps(
                {
                    "output": str(result.output),
                    "entries": result.entry_count,
                    "revisions": result.revision_count,
                },
                ensure_ascii=False,
            )
        )
        return 0
    print(
        f"{reason}. Output may be incomplete if created; inspect and retain it: "
        + json.dumps(output, ensure_ascii=False),
        file=sys.stderr,
    )
    return status


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
    export = commands.add_parser(
        "export-journal", help="Export originals and revisions to a new ZIP"
    )
    export.add_argument("--output", required=True, help="Absolute path; existing paths are refused")
    export.add_argument("--include-deleted", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.command == "export-journal":
        return _export(arguments.output, arguments.include_deleted)

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
