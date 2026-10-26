"""Restore guards and failure boundaries; no Docker or application DB required."""

import copy
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    import restore_checks as checks
    import restore_support as support

    SPEC = importlib.util.spec_from_file_location("smoke_restore", SCRIPTS / "smoke-restore.py")
    RESTORE = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(RESTORE)
finally:
    sys.path.pop(0)

RUN_ID = "a" * 32


class RestoreGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = support.Stack(
            f"life-archive-restore-{RUN_ID}-source", 18082, self.root / "s.env"
        )
        self.target = support.Stack(
            f"life-archive-restore-{RUN_ID}-target", 18083, self.root / "t.env"
        )
        self.docker = support.Docker(SCRIPTS.parent, self.root / "override.json", RUN_ID)

    def config(self):
        labels = {support.LABEL: RUN_ID}
        return {
            "name": self.source.project,
            "volumes": {
                name: {"name": self.source.project + "_" + name, "labels": labels}
                for name in ("pgdata", "media")
            },
            "networks": {
                "frontend": {"labels": labels},
                "database": {"labels": labels, "internal": True},
            },
            "services": {
                name: {
                    "labels": labels.copy(),
                    **(
                        {
                            "image": f"life-archive-restore-{RUN_ID}-"
                            + ("web" if name == "web" else "server")
                            + ":rehearsal",
                            "build": {"context": str(SCRIPTS.parent)},
                        }
                        if name != "postgres"
                        else {"image": "postgres:17.11-bookworm"}
                    ),
                }
                for name in ("api", "worker", "web", "postgres")
            },
        }

    def valid_config(self):
        config = self.config()
        config["services"]["web"]["ports"] = [
            {"host_ip": "127.0.0.1", "published": "18082", "target": 80}
        ]
        config["services"]["postgres"]["volumes"] = [
            {
                "type": "volume",
                "source": "pgdata",
                "target": "/var/lib/postgresql/data",
            }
        ]
        for name, read_only in (("api", False), ("worker", True)):
            config["services"][name]["volumes"] = [
                {
                    "type": "volume",
                    "source": "media",
                    "target": "/var/lib/lifearchive/media",
                    "read_only": read_only,
                }
            ]
            config["services"][name]["environment"] = {
                "LIFEARCHIVE_MEDIA_ROOT": "/var/lib/lifearchive/media"
            }
        return config

    def test_new_artifact_directory_and_environment_files_are_private(self):
        output = self.root / "new"
        with patch.object(RESTORE, "check_ports"):
            source, target, run_id = RESTORE.prepare(output, 18082, 18083)
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        self.assertEqual(support.validate_pair(source, target), run_id)
        for path in output.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(source.env_file.read_bytes(), target.env_file.read_bytes())
        self.assertIn("POSTGRES_PASSWORD=", source.env_file.read_text())

    def test_existing_artifact_paths_and_symlinks_are_unchanged(self):
        target = self.root / "keep"
        target.write_bytes(b"original")
        directory = self.root / "directory"
        directory.mkdir()
        link = self.root / "link"
        link.symlink_to(target)
        for path in (target, directory, link):
            with self.subTest(path=path), patch.object(RESTORE, "check_ports"):
                with self.assertRaises(FileExistsError):
                    RESTORE.prepare(path, 18082, 18083)
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(list(directory.iterdir()), [])
        self.assertTrue(link.is_symlink())
        with self.assertRaises(support.RestoreError):
            RESTORE.prepare(Path("relative"), 18082, 18083)

    def test_ports_must_be_distinct_unprivileged_and_unoccupied(self):
        for source, target in ((18082, 18082), (1, 18083), (18082, 65536)):
            with self.subTest(ports=(source, target)), self.assertRaises(support.RestoreError):
                support.check_ports(source, target)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            busy = listener.getsockname()[1]
            other = 18083 if busy != 18083 else 18084
            with self.assertRaises(support.RestoreError):
                support.check_ports(busy, other)

    def test_inherited_compose_and_database_settings_cannot_select_existing_data(self):
        with patch.dict(
            os.environ,
            {
                "POSTGRES_PASSWORD": "private-developer-secret",
                "POSTGRES_HOST": "real-database",
                "COMPOSE_FILE": "production.yaml",
                "COMPOSE_PROJECT_NAME": "production",
                "COMPOSE_ENV_FILES": "/private/production.env",
                "WEB_PORT": "8080",
                "LIFEARCHIVE_COOKIE_SECURE": "true",
                "NPM_REGISTRY": "invalid",
            },
        ):
            env = support.isolated_environment()
        self.assertEqual(env["COMPOSE_DISABLE_ENV_FILE"], "1")
        self.assertFalse(any(k.startswith(("POSTGRES_", "LIFEARCHIVE_")) for k in env))
        self.assertNotIn("COMPOSE_FILE", env)
        self.assertNotIn("COMPOSE_ENV_FILES", env)
        self.assertNotIn("COMPOSE_PROJECT_NAME", env)
        self.assertNotIn("WEB_PORT", env)

    def test_compose_always_uses_explicit_files_project_and_environment(self):
        with patch.object(self.docker, "run", return_value=b"ok") as run:
            self.docker.command(self.source, "config")
        args = run.call_args.args[0]
        self.assertIn("--env-file", args)
        self.assertEqual(args[args.index("--env-file") + 1], str(self.source.env_file))
        self.assertEqual(args[args.index("--project-name") + 1], self.source.project)
        self.assertEqual(args.count("--file"), 2)

    def test_invalid_or_identical_source_target_pairs_are_rejected(self):
        invalid = (
            self.source,
            support.Stack("production-target", 18083, self.target.env_file),
            support.Stack(f"life-archive-restore-{'b' * 32}-target", 18083, self.target.env_file),
            support.Stack(self.target.project, 18082, self.target.env_file),
            support.Stack(self.target.project, 18083, self.source.env_file),
        )
        for target in invalid:
            with self.subTest(target=target), self.assertRaises(support.RestoreError):
                support.validate_pair(self.source, target)

    def test_existing_named_or_labelled_objects_block_start(self):
        for kind in ("container", "network", "volume"):
            for labelled in (False, True):

                def result(args, kind=kind, labelled=labelled):
                    if args[0] != kind:
                        return b""
                    if labelled:
                        return b"existing-id" if "--quiet" in args else b"unrelated-name"
                    return (self.source.project + "_existing\n").encode()

                with (
                    self.subTest(kind=kind, labelled=labelled),
                    patch.object(
                        self.docker,
                        "run",
                        side_effect=result,
                    ) as run,
                ):
                    with self.assertRaises(support.RestoreError):
                        self.docker.start(self.source)
                    self.assertFalse(any("up" in call.args[0] for call in run.call_args_list))
                    self.assertEqual(self.docker.attempted, [])

    def test_config_rejects_external_volumes_public_db_ports_or_wrong_resources(self):
        valid = self.valid_config()
        with patch.object(self.docker, "command", return_value=json.dumps(valid).encode()):
            self.docker.validate_config(self.source)
        mutations = (
            lambda c: c["volumes"]["pgdata"].update(external=True),
            lambda c: c["volumes"]["pgdata"].update(name="production_pgdata"),
            lambda c: c["volumes"]["media"].update(external=True),
            lambda c: c["volumes"]["media"].update(name="production_media"),
            lambda c: c["services"]["worker"]["volumes"][0].update(read_only=False),
            lambda c: c["networks"]["database"].update(internal=False),
            lambda c: c["services"]["postgres"].update(ports=[{"published": "5432"}]),
            lambda c: c["services"]["web"]["ports"][0].update(host_ip="0.0.0.0"),
            lambda c: c["services"]["api"]["build"].update(context="/unrelated"),
            lambda c: c["services"]["postgres"].update(image="postgres:latest"),
            lambda c: c["services"]["postgres"]["volumes"][0].update(source="other"),
            lambda c: c["services"]["api"].update(labels={}),
        )
        for mutate in mutations:
            bad = copy.deepcopy(valid)
            mutate(bad)
            with (
                self.subTest(mutate=mutate),
                patch.object(
                    self.docker,
                    "command",
                    return_value=json.dumps(bad).encode(),
                ),
                self.assertRaises(support.RestoreError),
            ):
                self.docker.validate_config(self.source)

    def test_missing_docker_timeout_and_subprocess_failure_are_sanitized(self):
        for failure in (
            FileNotFoundError("private secret"),
            subprocess.TimeoutExpired("secret", 600),
        ):
            with (
                self.subTest(failure=failure),
                patch.object(
                    support.subprocess,
                    "run",
                    side_effect=failure,
                ),
                self.assertRaises(support.RestoreError) as caught,
            ):
                self.docker.run(["info"])
            self.assertNotIn("secret", str(caught.exception))
        failed = subprocess.CompletedProcess([], 1, b"private data", b"password=secret")
        with patch.object(support.subprocess, "run", return_value=failed) as run:
            with self.assertRaises(support.RestoreError) as caught:
                self.docker.run(["info"])
        self.assertNotIn("password", str(caught.exception))
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_nonempty_or_overlapping_database_never_receives_restore(self):
        dump = self.root / "archive.dump"
        dump.write_bytes(b"synthetic archive")
        for overlap, table_count in ((True, "0"), (False, "1")):

            def owned(stack, overlap=overlap):
                suffix = "same" if overlap else stack.project
                return {"container": suffix, "volume": suffix}

            with (
                self.subTest(overlap=overlap),
                patch.object(
                    self.docker,
                    "owned_pg",
                    side_effect=owned,
                ),
                patch.object(self.docker, "sql", return_value=table_count),
                patch.object(
                    self.docker,
                    "command",
                    return_value=b"",
                ) as command,
            ):
                with self.assertRaises(support.RestoreError):
                    RESTORE.restore(self.docker, self.source, self.target, dump)
                self.assertFalse(any("pg_restore" in call.args for call in command.call_args_list))

    def test_failed_restore_stops_without_destructive_retry_or_starting_application(self):
        dump = self.root / "archive.dump"
        dump.write_bytes(b"bad archive")
        with (
            patch.object(self.docker, "empty_target") as empty,
            patch.object(
                self.docker,
                "command",
                side_effect=support.RestoreError("restore failed"),
            ) as command,
        ):
            with self.assertRaises(support.RestoreError):
                RESTORE.restore(self.docker, self.source, self.target, dump)
        empty.assert_called_once_with(self.source, self.target)
        self.assertEqual(command.call_count, 1)
        args = command.call_args.args
        self.assertIn("--single-transaction", args)
        self.assertIn("--exit-on-error", args)
        self.assertNotIn("--clean", args)
        self.assertNotIn("up", args)

    def test_stop_refuses_any_container_without_matching_run_ownership(self):
        self.docker.attempted.append(self.source)
        with (
            patch.object(self.docker, "run", return_value=b"container-id\n"),
            patch.object(
                self.docker,
                "inspect",
                return_value={"Config": {"Labels": {}}},
            ),
            patch.object(self.docker, "command") as command,
        ):
            with self.assertRaises(support.RestoreError):
                self.docker.stop_owned()
        command.assert_not_called()

    def test_missing_docker_main_writes_failure_report_and_does_not_claim_success(self):
        output = self.root / "new"
        with (
            patch.object(RESTORE, "check_ports"),
            patch.object(
                support.subprocess,
                "run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "repository-sha", ""),
                    FileNotFoundError("private path"),
                ],
            ),
            patch("builtins.print"),
        ):
            self.assertEqual(RESTORE.main(["--artifact-dir", str(output)]), 1)
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["target_app_started"])
        self.assertNotIn("private path", json.dumps(report))

    def test_private_write_refuses_existing_symlink(self):
        existing = self.root / "existing"
        existing.write_bytes(b"preserve")
        link = self.root / "link"
        link.symlink_to(existing)
        with self.assertRaises(FileExistsError):
            support.private_write(link, b"new")
        self.assertEqual(existing.read_bytes(), b"preserve")


class PortableComparisonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def archive(
        self, name, content=b"original\r\n", exported_at="2026-10-25T00:00:00+00:00", bad_hash=False
    ):
        path = self.root / name
        member = "entries/00000000-0000-0000-0000-000000000001.md"
        manifest = {
            "schema_version": 3,
            "alembic_revision": "0005_private_images",
            "owner": {"id": "owner"},
            "deleted_policy": "include_deleted",
            "entry_count": 1,
            "revision_count": 0,
            "asset_count": 0,
            "exported_at": exported_at,
            "files": [
                {
                    "path": "assets.json",
                    "bytes": 3,
                    "sha256": hashlib.sha256(b"[]\n").hexdigest(),
                },
                {
                    "path": member,
                    "bytes": len(content),
                    "sha256": ("0" * 64 if bad_hash else hashlib.sha256(content).hexdigest()),
                },
                {
                    "path": "tags.json",
                    "bytes": 3,
                    "sha256": hashlib.sha256(b"[]\n").hexdigest(),
                },
            ],
        }
        with ZipFile(path, "w") as archive:
            archive.writestr(member, content)
            archive.writestr("tags.json", b"[]\n")
            archive.writestr("assets.json", b"[]\n")
            archive.writestr("manifest.json", json.dumps(manifest))
        return path

    def test_export_timestamp_can_differ_but_bytes_and_metadata_must_match(self):
        a = self.archive("a.zip")
        b = self.archive("b.zip", exported_at="2026-10-25T00:01:00+00:00")
        self.assertEqual(
            checks.compare_exports(a, b, "0005_private_images"),
            {
                "entries": 1,
                "revisions": 0,
                "assets": 0,
                "files": 3,
            },
        )
        changed = self.archive("changed.zip", content=b"changed")
        with self.assertRaises(support.RestoreError):
            checks.compare_exports(a, changed, "0005_private_images")
        with self.assertRaises(support.RestoreError):
            checks.compare_exports(a, b, "other_head")

    def test_corrupt_export_hash_is_rejected(self):
        a, b = self.archive("a.zip"), self.archive("bad.zip", bad_hash=True)
        with self.assertRaises(support.RestoreError):
            checks.compare_exports(a, b, "0005_private_images")


if __name__ == "__main__":
    unittest.main()
