#!/usr/bin/env python3
"""Prepare one isolated HTCondor build/test/plot job; never submit or process raw data."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess


def prepare(inputs, output, eic_shell, source):
    inputs, output, eic_shell, source = [Path(p).expanduser().resolve() for p in (inputs, output, eic_shell, source)]
    if output.exists():
        raise ValueError("Output exists; choose a fresh directory")
    if not eic_shell.is_file() or not os.access(eic_shell, os.X_OK):
        raise ValueError("eic-shell must be an executable file")
    runlist = source / "configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv"
    wrapper = source / "tools/run-in-eic-shell.sh"
    if not runlist.is_file() or not wrapper.is_file():
        raise ValueError("Source checkout is missing the run database or eic-shell wrapper")
    pairs, records = [], []
    for line in inputs.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2:
            raise ValueError("Input list needs calibration ROOT and waveform histogram ROOT on each line")
        pair = []
        for name in fields:
            path = Path(name)
            if not path.is_absolute():
                path = inputs.parent / path
            path = path.resolve()
            if any(c.isspace() for c in str(path)) or not path.is_file() or not path.stat().st_size:
                raise ValueError("Missing/empty input or unsupported whitespace path: " + str(path))
            st = path.stat()
            records.append({"path": str(path), "size": st.st_size, "mtime_ns": st.st_mtime_ns})
            pair.append(str(path))
        pairs.append(pair)
    if not pairs:
        raise ValueError("Input list has no file pairs")
    if len({tuple(pair) for pair in pairs}) != len(pairs):
        raise ValueError("Duplicate input pair")
    # Condor ClassAd strings below are deliberately restricted to ordinary paths.
    for path in (output, source, eic_shell):
        if any(c in str(path) for c in '\n\r"\\'):
            raise ValueError("Unsupported quote, backslash or newline in job path")
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Source has tracked edits; use a clean checkout")
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    output.mkdir(parents=True)
    (output / "rf_inputs.txt").write_text("".join(" ".join(pair) + "\n" for pair in pairs))
    (output / "inputs.json").write_text(json.dumps({"source": str(source), "head": head, "inputs": records}, indent=2) + "\n")
    q = lambda value: shlex.quote(str(value))
    build, plots = output / "build", output / "plots"
    payload = "#!/usr/bin/env bash\nset -euo pipefail\n"
    payload += '[[ -n ${_CONDOR_JOB_AD:-} ]] || { echo "Run through HTCondor, not on the login host" >&2; exit 2; }\n'
    payload += f"python3 {q(Path(__file__).resolve())} --verify {q(output / 'inputs.json')}\n"
    payload += f"cmake -S {q(source / 'NewStructure')} -B {q(build)} -DCMAKE_BUILD_TYPE=Release\n"
    payload += f"cmake --build {q(build)} --target CompareWaveform test_waveform_measurement test_ari_box_plot -j2\n"
    payload += f"ctest --test-dir {q(build)} --output-on-failure -R '^(waveform_measurement|ari_box_plot)$'\n"
    payload += f"mkdir {q(plots)}\n"
    payload += f"{q(build / 'CompareWaveform')} -A -I {q(output / 'rf_inputs.txt')} -r {q(runlist)} -o {q(output / 'ari_rf_comparison.root')} -O {q(plots)}\n"
    payload += f"python3 {q(Path(__file__).resolve())} --verify {q(output / 'inputs.json')}\n"
    for name in ("AriRF_WaveformMeasurementsMain.pdf", "AriRF_WaveformMeasurements.pdf", "AriRF_WaveformSummary.pdf", "AriRF_WaveformStatus.pdf"):
        payload += f"test -s {q(plots / name)}\n"
    (output / "payload.sh").write_text(payload)
    launch = "#!/usr/bin/env bash\nset -euo pipefail\n"
    launch += '[[ -n ${_CONDOR_JOB_AD:-} ]] || { echo "Submit job.sub with condor_submit" >&2; exit 2; }\n'
    launch += f"exec bash {q(wrapper)} {q(eic_shell)} bash {q(output / 'payload.sh')}\n"
    (output / "launch.sh").write_text(launch)
    (output / "launch.sh").chmod(0o755)
    (output / "job.sub").write_text(
        "universe = vanilla\n" + f'executable = "{output / "launch.sh"}"\n' +
        f'initialdir = "{output}"\noutput = job.out\nerror = job.err\nlog = job.log\n' +
        "getenv = True\nshould_transfer_files = NO\nrequest_cpus = 2\nrequest_memory = 4GB\nrequest_disk = 8GB\n+MaxRuntime = 7200\nqueue 1\n")
    return output / "job.sub"


def verify(manifest):
    data = json.loads(Path(manifest).read_text())
    current = subprocess.check_output(["git", "-C", data["source"], "rev-parse", "HEAD"], text=True).strip()
    if current != data["head"]:
        raise ValueError("Source checkout moved after job preparation")
    if subprocess.check_output(["git", "-C", data["source"], "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Source has tracked edits after job preparation")
    for item in data["inputs"]:
        st = Path(item["path"]).stat()
        if (st.st_size, st.st_mtime_ns) != (item["size"], item["mtime_ns"]):
            raise ValueError("Input changed after preparation: " + item["path"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--eic-shell", type=Path, default=Path(os.environ.get("EIC_SHELL", "/star/u/pnord/bin/eic-shell")))
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    try:
        if args.verify:
            verify(args.verify)
        else:
            if args.inputs is None or args.output is None:
                parser.error("--inputs and --output are required")
            job = prepare(args.inputs, args.output, args.eic_shell, Path(__file__).resolve().parents[2])
            print("Prepared one plot-only job (not submitted): " + str(job))
            print("Submit from tcsh: condor_submit " + shlex.quote(str(job)))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
