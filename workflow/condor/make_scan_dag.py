#!/usr/bin/env python3
"""Generate a matched-pedestal HTCondor DAG for HGCROC scan runs."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunRecord:
    run: int
    kind: str
    rf: str
    cf: str
    cc: str
    cfcomp: str

    @property
    def settings(self) -> tuple[str, str, str, str]:
        return self.rf, self.cf, self.cc, self.cfcomp


def parse_runs(path: Path) -> list[RunRecord]:
    records: list[RunRecord] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if not row or not row[0].strip().isdigit() or len(row) < 19:
                continue
            records.append(
                RunRecord(
                    run=int(row[0]),
                    kind=row[1].strip(),
                    rf=row[15].strip(),
                    cf=row[16].strip(),
                    cc=row[17].strip(),
                    cfcomp=row[18].strip(),
                )
            )
    return records


def matched_pairs(
    records: list[RunRecord],
) -> tuple[
    dict[int, tuple[RunRecord, RunRecord]],
    dict[int, tuple[RunRecord, RunRecord]],
]:
    pairs: dict[int, tuple[RunRecord, RunRecord]] = {}
    mismatches: dict[int, tuple[RunRecord, RunRecord]] = {}
    pedestal: RunRecord | None = None
    for record in records:
        kind = record.kind.lower()
        if "pedestal" in kind:
            pedestal = record
            continue
        if "muon" not in kind or pedestal is None:
            continue
        if record.settings == pedestal.settings:
            pairs[record.run] = pedestal, record
        else:
            mismatches[record.run] = pedestal, record
    return pairs, mismatches


def node_name(prefix: str, pedestal: int, muon: int) -> str:
    return f"{prefix}_{pedestal}_{muon}"


def add_job(lines: list[str], submit: Path, node: str, phase: str,
            pedestal: int, muon: int, cpus: int, memory: str) -> None:
    lines.append(f"JOB {node} {submit}")
    lines.append(
        f'VARS {node} node="{node}" phase="{phase}" '
        f'pedestal="{pedestal}" muon="{muon}" '
        f'cpus="{cpus}" memory="{memory}"'
    )
    lines.append(f"RETRY {node} 1")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-db", required=True, type=Path)
    parser.add_argument("--submit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--runs", nargs="+", type=int, required=True)
    parser.add_argument(
        "--minimum-muon-bytes",
        type=int,
        default=10_000_000,
        help="Refuse suspiciously small converted muon files",
    )
    args = parser.parse_args()

    if not args.submit.is_file():
        raise SystemExit(f"Missing submit description: {args.submit}")
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite DAG: {args.output}")

    pairs, mismatches = matched_pairs(parse_runs(args.run_db))
    lines = ["# Generated matched-pedestal HGCROC scan DAG"]

    for muon_run in args.runs:
        if muon_run in mismatches:
            pedestal, muon = mismatches[muon_run]
            raise SystemExit(
                f"Run {muon.run} settings {muon.settings} do not match "
                f"preceding pedestal {pedestal.run} settings {pedestal.settings}"
            )
        if muon_run not in pairs:
            raise SystemExit(f"No matched pedestal found for muon run {muon_run}")
        pedestal, muon = pairs[muon_run]

        raw_ped = args.data_dir / f"rawHGCROC_{pedestal.run}_offlinefix_batch.root"
        raw_muon = args.data_dir / f"rawHGCROC_{muon.run}_offlinefix_batch.root"
        for raw in (raw_ped, raw_muon):
            if not raw.is_file():
                raise SystemExit(f"Missing converted input: {raw}")
        if raw_muon.stat().st_size < args.minimum_muon_bytes:
            raise SystemExit(
                f"Refusing small muon input ({raw_muon.stat().st_size} bytes): {raw_muon}"
            )
        production_dir = args.data_dir / f"prod_{pedestal.run}_{muon.run}"
        if production_dir.exists():
            raise SystemExit(f"Refusing existing production directory: {production_dir}")

        ped_node = node_name("PED", pedestal.run, muon.run)
        cal_node = node_name("CAL", pedestal.run, muon.run)
        apply_node = node_name("APPLY", pedestal.run, muon.run)
        wave_node = node_name("WAVE", pedestal.run, muon.run)

        add_job(lines, args.submit, ped_node, "pedestal", pedestal.run, muon.run, 1, "4GB")
        add_job(lines, args.submit, cal_node, "calibration", pedestal.run, muon.run, 1, "8GB")
        add_job(lines, args.submit, apply_node, "apply", pedestal.run, muon.run, 1, "8GB")
        add_job(lines, args.submit, wave_node, "waveform", pedestal.run, muon.run, 4, "8GB")

        lines.append(f"PARENT {ped_node} CHILD {cal_node}")
        lines.append(f"PARENT {cal_node} CHILD {apply_node}")
        lines.append(f"PARENT {apply_node} CHILD {wave_node}")
        lines.append("")

    for run in args.runs:
        pedestal, _ = pairs[run]
        lines.append(
            f"CATEGORY {node_name('PED', pedestal.run, run)} PEDESTAL"
        )
        lines.append(
            f"CATEGORY {node_name('CAL', pedestal.run, run)} CALIBRATION"
        )
        lines.append(
            f"CATEGORY {node_name('APPLY', pedestal.run, run)} APPLY"
        )
        lines.append(
            f"CATEGORY {node_name('WAVE', pedestal.run, run)} WAVEFORM"
        )
    lines.extend([
        "MAXJOBS PEDESTAL 8",
        "MAXJOBS CALIBRATION 4",
        "MAXJOBS APPLY 4",
        "MAXJOBS WAVEFORM 4",
        "",
    ])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.output}")
    for muon_run in args.runs:
        pedestal, muon = pairs[muon_run]
        print(
            f"ped {pedestal.run} -> muon {muon.run}: "
            f"RF={muon.rf} CF={muon.cf} CC={muon.cc} CFComp={muon.cfcomp}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
