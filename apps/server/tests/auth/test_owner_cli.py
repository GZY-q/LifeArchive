from io import StringIO

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from life_archive import cli
from life_archive.auth.models import User
from life_archive.auth.security import verify_password
from life_archive.auth.service import OwnerSetupError, create_owner


def test_cli_reads_password_from_stdin_without_echo_and_refuses_second_owner(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    password = "stdin-only-test-passphrase"
    monkeypatch.setattr(cli, "get_session_factory", lambda: session_factory)
    arguments = [
        "init-owner",
        "--username",
        "owner",
        "--timezone",
        "Asia/Shanghai",
        "--password-stdin",
    ]
    monkeypatch.setattr("sys.stdin", StringIO(password + "\n"))
    assert cli.main(arguments) == 0
    output = capsys.readouterr()
    assert password not in output.out + output.err
    with session_factory() as db:
        user = db.scalar(select(User))
        assert user is not None and user.timezone == "Asia/Shanghai"
        assert verify_password(user.password_hash, password)
        original_hash = user.password_hash

    monkeypatch.setattr("sys.stdin", StringIO("different-test-passphrase\n"))
    assert cli.main(arguments) == 1
    assert "already exists" in capsys.readouterr().err
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(User.password_hash)) == original_hash


def test_cli_prompts_twice_and_rejects_mismatched_passwords(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter(["first-private-value", "second-private-value"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(answers))
    assert cli.main(["init-owner", "--username", "owner"]) == 1
    output = capsys.readouterr()
    assert "do not match" in output.err
    assert "private-value" not in output.out + output.err


@pytest.mark.parametrize("singleton", [True, False])
def test_database_constraints_prevent_any_second_owner(
    owner: User, db_session: Session, singleton: bool
) -> None:
    db_session.add(
        User(
            username="second-owner",
            password_hash=owner.password_hash,
            timezone="UTC",
            singleton=singleton,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_invalid_owner_input_cannot_create_a_row(db_session: Session) -> None:
    with pytest.raises(OwnerSetupError):
        create_owner(db_session, "owner", "too-short", "invalid-zone")
    assert db_session.scalar(select(func.count()).select_from(User)) == 0
