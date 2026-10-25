"""Compose guards used only by the synthetic restore rehearsal."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

LABEL = "life_archive.restore_run"


class RestoreError(Exception):
    """Fixed public diagnostics; never include subprocess output or source data."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise RestoreError(message)


def private_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(data)


def isolated_environment() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("POSTGRES_", "LIFEARCHIVE_", "COMPOSE_"))
        and key not in {"WEB_PORT", "NPM_REGISTRY"}
    }
    env["COMPOSE_DISABLE_ENV_FILE"] = "1"
    return env


def check_ports(source: int, target: int) -> None:
    require(
        source != target and all(1024 <= port <= 65535 for port in (source, target)),
        "Use distinct unprivileged loopback ports",
    )
    for port in (source, target):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", port))
        except OSError:
            raise RestoreError("A requested loopback port is unavailable") from None


@dataclass(frozen=True)
class Stack:
    project: str
    port: int
    env_file: Path


def validate_pair(source: Stack, target: Stack) -> str:
    pattern = r"life-archive-restore-([0-9a-f]{32})-(source|target)"
    left, right = re.fullmatch(pattern, source.project), re.fullmatch(pattern, target.project)
    require(left and right, "Invalid rehearsal project identities")
    assert left is not None and right is not None
    require(
        left[1] == right[1] and left[2] == "source" and right[2] == "target",
        "Source and target must be distinct projects from this run",
    )
    require(
        source.env_file != target.env_file and source.port != target.port,
        "Source and target configuration must be distinct",
    )
    return left[1]


class Docker:
    def __init__(self, repo: Path, override: Path, run_id: str):
        self.repo, self.override, self.run_id = repo, override, run_id
        self.env = isolated_environment()
        self.phase = "preflight"
        self.attempted: list[Stack] = []

    def run(
        self,
        args: list[str],
        *,
        data: bytes | None = None,
        output: BinaryIO | None = None,
        input_file: BinaryIO | None = None,
    ) -> bytes:
        try:
            process = subprocess.run(
                ["docker", *args],
                cwd=self.repo,
                env=self.env,
                input=data,
                stdin=input_file,
                stdout=output if output is not None else subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=600,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RestoreError("Docker unavailable or timed out during " + self.phase) from None
        require(process.returncode == 0, "Docker command failed during " + self.phase)
        return process.stdout or b""

    def command(
        self,
        stack: Stack,
        *args: str,
        data: bytes | None = None,
        output: BinaryIO | None = None,
        input_file: BinaryIO | None = None,
    ) -> bytes:
        return self.run(
            [
                "compose",
                "--file",
                str(self.repo / "compose.yaml"),
                "--file",
                str(self.override),
                "--project-directory",
                str(self.repo),
                "--env-file",
                str(stack.env_file),
                "--project-name",
                stack.project,
                *args,
            ],
            data=data,
            output=output,
            input_file=input_file,
        )

    def inspect(self, kind: str, name: str) -> dict:
        return json.loads(self.run([kind, "inspect", name]))[0]

    def preflight(self, stack: Stack) -> None:
        for kind in ("container", "network", "volume"):
            all_option = ["--all"] if kind == "container" else []
            names = (
                self.run(
                    [
                        kind,
                        "ls",
                        *all_option,
                        "--format",
                        "{{.Names}}" if kind == "container" else "{{.Name}}",
                    ]
                )
                .decode()
                .splitlines()
            )
            require(
                not any(
                    name == stack.project
                    or name.startswith((stack.project + "-", stack.project + "_"))
                    for name in names
                ),
                "Existing rehearsal-named Docker object; refusing reuse",
            )
            labels = self.run(
                [
                    kind,
                    "ls",
                    *all_option,
                    "--quiet",
                    "--filter",
                    "label=com.docker.compose.project=" + stack.project,
                ]
            )
            require(not labels.strip(), "Existing Compose project; refusing reuse")

    def validate_config(self, stack: Stack) -> dict:
        config = json.loads(
            self.command(stack, "--profile", "worker", "config", "--format", "json")
        )
        require(config["name"] == stack.project, "Unexpected Compose project")
        services = config["services"]
        require(set(services) == {"api", "web", "postgres", "worker"}, "Unexpected services")
        require(set(config["networks"]) == {"frontend", "database"}, "Unexpected networks")
        require(
            config["volumes"]["pgdata"]["name"] == stack.project + "_pgdata",
            "Unexpected database volume",
        )
        for resource in (config["volumes"]["pgdata"], *config["networks"].values()):
            require(
                not resource.get("external")
                and resource.get("labels", {}).get(LABEL) == self.run_id,
                "External or unowned Compose resource",
            )
        require(
            config["networks"]["database"]["internal"] is True, "Database network must be internal"
        )
        for name, service in services.items():
            require(
                service.get("labels", {}).get(LABEL) == self.run_id, "Unowned service configuration"
            )
            if name == "web":
                ports = service.get("ports", [])
                require(
                    len(ports) == 1
                    and ports[0]["host_ip"] == "127.0.0.1"
                    and str(ports[0]["published"]) == str(stack.port)
                    and ports[0]["target"] == 80,
                    "Unexpected web port binding",
                )
            else:
                require(not service.get("ports"), "Private service publishes a port")
        require(
            services["postgres"]["image"] == "postgres:17.11-bookworm",
            "Unexpected PostgreSQL image",
        )
        mount = services["postgres"]["volumes"]
        require(
            len(mount) == 1
            and mount[0]["type"] == "volume"
            and mount[0]["source"] == "pgdata"
            and mount[0]["target"] == "/var/lib/postgresql/data",
            "Unexpected PG storage",
        )
        for name in ("api", "worker", "web"):
            suffix = "web" if name == "web" else "server"
            require(
                services[name]["image"] == f"life-archive-restore-{self.run_id}-{suffix}:rehearsal",
                "Rehearsal must use its own image tags",
            )
            require(
                Path(services[name]["build"]["context"]) == self.repo, "Unexpected build context"
            )
        return config

    def start(self, stack: Stack, *, database_only: bool = False, build: bool = False) -> None:
        self.preflight(stack)
        self.attempted.append(stack)
        flags = ["--build"] if build else ["--no-build", "--pull", "never"]
        self.command(
            stack,
            "up",
            "--detach",
            "--wait",
            "--wait-timeout",
            "180",
            *flags,
            *(["postgres"] if database_only else []),
        )

    def owned_pg(self, stack: Stack) -> dict:
        container_id = self.command(stack, "ps", "--all", "--quiet", "postgres").decode().strip()
        require(re.fullmatch(r"[0-9a-f]{12,64}", container_id), "Expected one PostgreSQL container")
        container = self.inspect("container", container_id)
        self.check_labels(container["Config"]["Labels"], stack)
        require(
            container["Config"]["Labels"]["com.docker.compose.service"] == "postgres",
            "Unexpected database service identity",
        )
        require(not container["HostConfig"].get("PortBindings"), "PostgreSQL port is published")
        volume_name = stack.project + "_pgdata"
        mounts = container["Mounts"]
        require(
            len(mounts) == 1
            and mounts[0]["Type"] == "volume"
            and mounts[0]["Name"] == volume_name
            and mounts[0]["Destination"] == "/var/lib/postgresql/data",
            "Unexpected live PG volume",
        )
        self.check_labels(self.inspect("volume", volume_name)["Labels"], stack)
        network_name = stack.project + "_database"
        require(
            set(container["NetworkSettings"]["Networks"]) == {network_name}, "Unexpected PG network"
        )
        network = self.inspect("network", network_name)
        require(network["Internal"] is True, "Live database network is not internal")
        self.check_labels(network["Labels"], stack)
        return {"container": container_id, "volume": volume_name, "image": container["Image"]}

    def check_labels(self, labels: dict | None, stack: Stack) -> None:
        require(
            labels
            and labels.get(LABEL) == self.run_id
            and labels.get("com.docker.compose.project") == stack.project,
            "Docker ownership mismatch; refusing operation",
        )

    def sql(self, stack: Stack, statement: str) -> str:
        return (
            self.command(
                stack,
                "exec",
                "-T",
                "postgres",
                "psql",
                "--no-psqlrc",
                "--set=ON_ERROR_STOP=1",
                "--tuples-only",
                "--no-align",
                "--username=life_archive",
                "--dbname=life_archive_restore",
                "--command",
                statement,
            )
            .decode()
            .strip()
        )

    def empty_target(self, source: Stack, target: Stack) -> None:
        left, right = self.owned_pg(source), self.owned_pg(target)
        require(
            left["container"] != right["container"] and left["volume"] != right["volume"],
            "Source and target database identities overlap",
        )
        for service in ("api", "web"):
            require(
                not self.command(target, "ps", "--all", "--quiet", service).strip(),
                "Target application already exists before restore",
            )
        count = self.sql(
            target,
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname NOT IN "
            "('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' "
            "AND c.relkind IN ('r','p','v','m','S','f')",
        )
        require(count == "0", "Target database is not empty; refusing restore")

    def stop_owned(self) -> None:
        for stack in reversed(self.attempted):
            ids = (
                self.run(
                    [
                        "container",
                        "ls",
                        "--all",
                        "--quiet",
                        "--filter",
                        "label=com.docker.compose.project=" + stack.project,
                    ]
                )
                .decode()
                .splitlines()
            )
            if not ids:
                continue
            for container_id in ids:
                self.check_labels(
                    self.inspect("container", container_id)["Config"]["Labels"], stack
                )
            self.owned_pg(stack)
            self.command(stack, "stop")
