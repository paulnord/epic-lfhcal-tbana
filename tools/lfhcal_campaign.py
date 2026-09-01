#!/usr/bin/env python3
"""Shared helpers for generating LFHCal campaign manifests."""

from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass, field


JOB_NAME = re.compile(r"^[A-Za-z0-9_.+-]+$")


def logical_cwd() -> pathlib.Path:
    """Return cwd while preserving a logical /star path when possible."""
    physical = pathlib.Path.cwd()
    shell_pwd = os.environ.get("PWD")
    if shell_pwd:
        candidate = pathlib.Path(shell_pwd).expanduser()
        try:
            if candidate.is_absolute() and os.path.samefile(candidate, physical):
                return pathlib.Path(os.path.normpath(str(candidate)))
        except OSError:
            pass
    return physical


def absolute_path(value: str | pathlib.Path, base: pathlib.Path) -> pathlib.Path:
    """Make a path absolute without resolving logical mounts or symlinks."""
    path = pathlib.Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return pathlib.Path(os.path.abspath(path))


def parse_runs(specifications: Sequence[str]) -> list[int]:
    """Expand run numbers and inclusive ranges, preserving order."""
    runs: list[int] = []
    seen: set[int] = set()
    for specification in specifications:
        parts = specification.split("-", maxsplit=1)
        try:
            first = int(parts[0])
            last = int(parts[1]) if len(parts) == 2 else first
        except ValueError as error:
            raise ValueError(f"invalid run or range: {specification!r}") from error
        if first <= 0 or last <= 0:
            raise ValueError(f"run numbers must be positive: {specification!r}")
        if last < first:
            raise ValueError(f"run range must be ascending: {specification!r}")
        for run in range(first, last + 1):
            if run not in seen:
                runs.append(run)
                seen.add(run)
    return runs


@dataclass
class Job:
    name: str
    command: Sequence[str | pathlib.Path]
    inputs: Sequence[tuple[str, pathlib.Path]] = ()
    outputs: Sequence[tuple[str, pathlib.Path]] = ()
    parents: list[str] = field(default_factory=list)
    retries: int = 1

    def render(self) -> str:
        tokens: list[str] = ["JOB", self.name]
        for role, path in self.inputs:
            tokens.extend(("--input", f"{role}={path}"))
        for role, path in self.outputs:
            tokens.extend(("--output", f"{role}={path}"))
        tokens.append("--")
        tokens.extend(str(item) for item in self.command)
        return shlex.join(tokens)


def job_line(
    name: str,
    command: Sequence[str | pathlib.Path],
    *,
    inputs: Sequence[tuple[str, pathlib.Path]] = (),
    outputs: Sequence[tuple[str, pathlib.Path]] = (),
) -> str:
    """Render one JOB line; retained for simple and legacy generators."""
    return Job(name, command, inputs, outputs, retries=0).render()


def _toml_string(value: str | pathlib.Path) -> str:
    """Render a TOML basic string using JSON-compatible escaping."""
    return json.dumps(str(value))


def _toml_string_array(values: Sequence[str | pathlib.Path]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _toml_file_refs(values: Sequence[tuple[str, pathlib.Path]]) -> str:
    return "[" + ", ".join(
        "{ role = " + _toml_string(role) + ", path = " + _toml_string(path) + " }"
        for role, path in values
    ) + "]"


class Campaign:
    """Small validated builder for LFHCal workflow descriptions."""

    def __init__(self, comments: Sequence[str] = ()) -> None:
        self.comments = list(comments)
        self.jobs: list[Job] = []
        self._by_name: dict[str, Job] = {}

    def add_job(
        self,
        name: str,
        command: Sequence[str | pathlib.Path],
        *,
        inputs: Sequence[tuple[str, pathlib.Path]] = (),
        outputs: Sequence[tuple[str, pathlib.Path]] = (),
        parents: Sequence[str] = (),
        retries: int = 1,
    ) -> Job:
        if not JOB_NAME.fullmatch(name):
            raise ValueError(f"invalid job name: {name!r}")
        if name in self._by_name:
            raise ValueError(f"duplicate job name: {name}")
        if not command:
            raise ValueError(f"job {name!r} has no command")
        if retries < 0:
            raise ValueError(f"job {name!r} has a negative retry count")
        job = Job(name, command, inputs, outputs, list(parents), retries)
        self.jobs.append(job)
        self._by_name[name] = job
        return job

    def validate(self) -> None:
        for job in self.jobs:
            unknown = [parent for parent in job.parents if parent not in self._by_name]
            if unknown:
                raise ValueError(f"job {job.name!r} has unknown parents: {', '.join(unknown)}")

        state: dict[str, int] = {}

        def visit(name: str) -> None:
            if state.get(name) == 1:
                raise ValueError(f"dependency cycle involving {name!r}")
            if state.get(name) == 2:
                return
            state[name] = 1
            for parent in self._by_name[name].parents:
                visit(parent)
            state[name] = 2

        for name in self._by_name:
            visit(name)

    def render(self) -> str:
        """Render the legacy lfhcal-run JOB/PARENT/RETRY manifest."""
        self.validate()
        lines = [f"# {comment}" for comment in self.comments]
        if lines:
            lines.append("")
        lines.extend(job.render() for job in self.jobs)

        dependencies: dict[tuple[str, ...], list[str]] = {}
        for job in self.jobs:
            if job.parents:
                dependencies.setdefault(tuple(job.parents), []).append(job.name)
        if dependencies:
            lines.append("")
            for parents, children in dependencies.items():
                lines.append(
                    "PARENT " + " ".join(parents) + " CHILD " + " ".join(children)
                )

        retries = [job for job in self.jobs if job.retries]
        if retries:
            lines.append("")
            lines.extend(f"RETRY {job.name} {job.retries}" for job in retries)
        lines.append("")
        return "\n".join(lines)

    def render_yawl(
        self,
        name: str,
        *,
        backend: str = "condor",
        cwd: pathlib.Path | None = None,
        condor_wrapper: pathlib.Path | None = None,
        request_cpus: int = 1,
        request_memory: str = "4GB",
        request_disk: str = "2GB",
    ) -> str:
        """Render this campaign as a YAWL-run TOML specification."""
        self.validate()
        if backend not in {"local", "condor"}:
            raise ValueError("YAWL backend must be 'local' or 'condor'")
        if request_cpus < 1:
            raise ValueError("YAWL Condor request_cpus must be positive")

        lines = [f"# {comment}" for comment in self.comments]
        if lines:
            lines.append("")
        lines.extend(
            [
                "[campaign]",
                f"name = {_toml_string(name)}",
                f"backend = {_toml_string(backend)}",
            ]
        )
        if backend == "condor":
            lines.extend(
                [
                    "",
                    "[condor]",
                    f"request_cpus = {request_cpus}",
                    f"request_memory = {_toml_string(request_memory)}",
                    f"request_disk = {_toml_string(request_disk)}",
                    "getenv = true",
                ]
            )
            if condor_wrapper is not None:
                lines.append(f"wrapper = {_toml_string(condor_wrapper)}")

        for job in self.jobs:
            lines.extend(
                [
                    "",
                    "[[task]]",
                    f"name = {_toml_string(job.name)}",
                ]
            )
            if cwd is not None:
                lines.append(f"cwd = {_toml_string(cwd)}")
            lines.append(
                "command = " + _toml_string_array([str(item) for item in job.command])
            )
            if job.parents:
                lines.append("parents = " + _toml_string_array(job.parents))
            if job.retries:
                lines.append(f"retries = {job.retries}")
            if job.inputs:
                lines.append("inputs = " + _toml_file_refs(job.inputs))
            if job.outputs:
                lines.append("outputs = " + _toml_file_refs(job.outputs))

        lines.append("")
        return "\n".join(lines)


def _write_text(
    destination: pathlib.Path,
    text: str,
    *,
    force: bool,
    tool_name: str,
) -> None:
    if destination.exists() and not force:
        raise FileExistsError(
            f"{tool_name}: {destination} already exists; use --force to replace it"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def write_manifest(
    campaign: Campaign,
    destination: pathlib.Path,
    *,
    force: bool,
    tool_name: str,
) -> None:
    _write_text(
        destination,
        campaign.render(),
        force=force,
        tool_name=tool_name,
    )


def write_yawl_manifest(
    campaign: Campaign,
    destination: pathlib.Path,
    *,
    name: str,
    force: bool,
    tool_name: str,
    backend: str = "condor",
    cwd: pathlib.Path | None = None,
    condor_wrapper: pathlib.Path | None = None,
    request_cpus: int = 1,
    request_memory: str = "4GB",
    request_disk: str = "2GB",
) -> None:
    _write_text(
        destination,
        campaign.render_yawl(
            name,
            backend=backend,
            cwd=cwd,
            condor_wrapper=condor_wrapper,
            request_cpus=request_cpus,
            request_memory=request_memory,
            request_disk=request_disk,
        ),
        force=force,
        tool_name=tool_name,
    )


def missing_files(paths: Sequence[pathlib.Path]) -> list[pathlib.Path]:
    return [path for path in paths if not path.is_file()]
