"""Restore only this script's new synthetic Compose source into its new empty target."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from restore_checks import Client, compare_exports, file_sha256
from restore_support import (
    LABEL,
    Docker,
    RestoreError,
    Stack,
    check_ports,
    private_write,
    require,
    validate_pair,
)

REPO = Path(__file__).resolve().parents[1]


def prepare(directory: Path, source_port: int, target_port: int) -> tuple[Stack, Stack, str]:
    require(directory.is_absolute(), "Artifact directory must be an absolute new path")
    check_ports(source_port, target_port)
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    run_id = secrets.token_hex(16)
    stacks = []
    for role, port in (("source", source_port), ("target", target_port)):
        env = (
            f"POSTGRES_USER=life_archive\nPOSTGRES_DB=life_archive_restore\n"
            f"POSTGRES_PASSWORD={secrets.token_hex(32)}\nWEB_PORT={port}\n"
            "LIFEARCHIVE_COOKIE_SECURE=false\n"
            f"LIFEARCHIVE_TRUSTED_ORIGINS='[\"http://127.0.0.1:{port}\"]'\n"
        )
        env_file = directory / (role + ".env")
        private_write(env_file, env.encode())
        stacks.append(Stack(f"life-archive-restore-{run_id}-{role}", port, env_file))
    labels = {LABEL: run_id}
    override = {
        "services": {
            name: {
                "labels": labels,
                **(
                    {
                        "image": f"life-archive-restore-{run_id}-"
                        + ("web" if name == "web" else "server")
                        + ":rehearsal"
                    }
                    if name != "postgres"
                    else {}
                ),
            }
            for name in ("api", "worker", "web", "postgres")
        },
        "networks": {name: {"labels": labels} for name in ("frontend", "database")},
        "volumes": {"pgdata": {"labels": labels}},
    }
    private_write(directory / "compose.images.json", json.dumps(override).encode())
    return stacks[0], stacks[1], run_id


def helper(docker: Docker, stack: Stack, action: str, password: str | None = None) -> dict:
    code = (REPO / "scripts/restore_fixture.py").read_text()
    data = json.dumps({"password": password}).encode() if password else None
    return json.loads(
        docker.command(stack, "exec", "-T", "api", "python", "-c", code, action, data=data)
    )


def export(docker: Docker, stack: Stack, directory: Path) -> Path:
    internal = "/tmp/restore-" + docker.run_id + ".zip"
    docker.command(
        stack,
        "exec",
        "-T",
        "api",
        "python",
        "-m",
        "life_archive.cli",
        "export-journal",
        "--output",
        internal,
        "--include-deleted",
    )
    path = directory / (
        "source-export.zip" if stack.project.endswith("-source") else "target-export.zip"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        docker.command(
            stack,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import shutil,sys; f=open(sys.argv[1],'rb'); shutil.copyfileobj(f,sys.stdout.buffer)",
            internal,
            output=output,
        )
    return path


def restore(docker: Docker, source: Stack, target: Stack, dump: Path) -> None:
    require(validate_pair(source, target) == docker.run_id, "Unexpected restore run identity")
    docker.empty_target(source, target)
    # Never clean a target or retry with destructive flags after failure.
    with dump.open("rb") as data:
        docker.command(
            target,
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-acl",
            "--username=life_archive",
            "--dbname=life_archive_restore",
            input_file=data,
        )


def rehearse(
    docker: Docker, source: Stack, target: Stack, directory: Path, report: dict, corrupt: bool
) -> None:
    require(validate_pair(source, target) == docker.run_id, "Unexpected rehearsal run identity")
    docker.run(["info", "--format", "{{json .ServerVersion}}"])
    for stack in (source, target):
        docker.preflight(stack)
        docker.validate_config(stack)
    docker.phase = "start source"
    docker.start(source, build=True)
    source_pg = docker.owned_pg(source)
    docker.command(source, "exec", "-T", "api", "alembic", "upgrade", "head")
    password = secrets.token_hex(32)
    private_write(directory / "owner-password.txt", password.encode())
    ids = helper(docker, source, "seed", password)
    baseline = helper(docker, source, "snapshot")
    require(baseline["heads"] == [baseline["expected_head"]], "Source migration mismatch")
    require(
        baseline["counts"] == {"entries": 3, "entry_revisions": 6, "deleted": 1},
        "Fixture counts mismatch",
    )
    report.update({"migration": baseline["expected_head"], "counts": baseline["counts"]})
    client_source = Client(source.port)
    owner = client_source.login(password)
    views = client_source.views(ids)
    source_export = export(docker, source, directory)
    print(
        "PASS: isolated source initialized; originals, revisions and portable export ready",
        flush=True,
    )
    docker.phase = "dump source"
    dump = directory / "database.dump"
    descriptor = os.open(dump, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        docker.command(
            source,
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--username=life_archive",
            "--dbname=life_archive_restore",
            output=output,
        )
    report["dump_sha256"] = file_sha256(dump)
    docker.phase = "start empty target"
    docker.start(target, database_only=True)
    target_pg = docker.owned_pg(target)
    require(source_pg["image"] == target_pg["image"], "PostgreSQL image identities differ")
    report["postgres_image"] = source_pg["image"]
    report["postgres_version"] = docker.sql(source, "SHOW server_version")
    require(
        report["postgres_version"] == docker.sql(target, "SHOW server_version"),
        "PG versions differ",
    )
    if corrupt:
        dump = directory / "corrupt-test.dump"
        private_write(dump, b"synthetic invalid PostgreSQL archive\n")
    docker.phase = "restore database"
    try:
        restore(docker, source, target, dump)
    except RestoreError:
        if corrupt:
            docker.empty_target(source, target)
            require(helper(docker, source, "snapshot") == baseline, "Source changed after refusal")
            report["checks"].update(
                {
                    "corrupt_dump_refused": True,
                    "target_still_empty": True,
                    "source_unchanged": True,
                }
            )
        raise
    report["checks"]["empty_target_and_restore"] = True
    docker.phase = "start restored application"
    docker.command(
        target, "up", "--detach", "--wait", "--wait-timeout", "180", "--no-build", "--pull", "never"
    )
    report["target_app_started"] = True
    restored = helper(docker, target, "snapshot")
    require(restored == baseline, "Restored journal, owner or migration snapshot differs")
    report["checks"]["same_journal_owner_migration"] = True
    client_target = Client(target.port)
    require(client_target.login(password) == owner, "Restored owner login differs")
    require(client_target.views(ids) == views, "Restored HTTP views differ")
    report["checks"]["restored_auth_and_views"] = True
    report["portable"] = compare_exports(
        source_export, export(docker, target, directory), baseline["expected_head"]
    )
    report["checks"]["same_portable_bytes_hashes"] = True
    docker.phase = "restart target PostgreSQL"
    docker.command(target, "restart", "postgres")
    docker.command(
        target, "up", "--detach", "--wait", "--wait-timeout", "180", "--no-build", "--pull", "never"
    )
    docker.owned_pg(target)
    require(helper(docker, target, "snapshot") == baseline, "Snapshot changed after restart")
    require(client_target.views(ids) == views, "Restored HTTP reads failed after restart")
    report["checks"]["postgres_restart"] = True
    require(
        helper(docker, source, "snapshot") == baseline, "Source journal changed during rehearsal"
    )
    report["checks"]["source_unchanged"] = True
    report["server_image"] = docker.inspect(
        "container", docker.command(source, "ps", "--quiet", "api").decode().strip()
    )["Image"]
    require(
        report["server_image"]
        == docker.inspect(
            "container", docker.command(target, "ps", "--quiet", "api").decode().strip()
        )["Image"],
        "API image identities differ",
    )
    print(
        "PASS: restore, exact originals/revisions, owner login, exports, HTTP views and PG restart",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--source-port", type=int, default=18082)
    parser.add_argument("--target-port", type=int, default=18083)
    parser.add_argument(
        "--corrupt-test-dump",
        action="store_true",
        help="Generate a new damaged fixture; expect failure before target app start",
    )
    args = parser.parse_args(argv)
    try:
        source, target, run_id = prepare(args.artifact_dir, args.source_port, args.target_port)
    except Exception:
        print(
            "Restore rehearsal refused: use a new absolute artifact directory "
            "and free distinct ports"
        )
        return 1
    docker = Docker(REPO, args.artifact_dir / "compose.images.json", run_id)
    report = {
        "status": "failed",
        "run_id": run_id,
        "artifact_dir": str(args.artifact_dir),
        "date_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 -- host Python 3.9
        "revision": None,
        "source_project": source.project,
        "target_project": target.project,
        "source_volume": source.project + "_pgdata",
        "target_volume": target.project + "_pgdata",
        "source_port": source.port,
        "target_port": target.port,
        "negative_fixture": args.corrupt_test_dump,
        "target_app_started": False,
        "checks": {},
        "cleanup": "stop only; retain containers, volumes and private artifacts",
    }
    status = 1
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False
        )
        require(revision.returncode == 0, "Cannot identify repository revision")
        report["revision"] = revision.stdout.strip()
        rehearse(docker, source, target, args.artifact_dir, report, args.corrupt_test_dump)
        report["status"], status = "passed", 0
    except KeyboardInterrupt:
        report["error"], status = "Interrupted", 130
    except Exception as error:
        report["error"] = (
            str(error) if isinstance(error, RestoreError) else "Rehearsal operation failed"
        )
    finally:
        report["last_phase"] = docker.phase
        docker.phase = "stop owned projects"
        try:
            docker.stop_owned()
            report["checks"]["owned_projects_stopped"] = True
        except Exception:
            report["status"], status = "failed", 1
            report["checks"]["owned_projects_stopped"] = False
        private_write(args.artifact_dir / "report.json", json.dumps(report, indent=2).encode())
    print(json.dumps(report, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
