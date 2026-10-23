# LFHCal baseline smoke tests

A quick, explicit check of the **already-built** LFHCal stack. The runner never
installs packages, rebuilds the project, downloads raw data, starts a campaign,
or submits a batch job. Keep full detector/fit regression tests separate.

## One command after compilation

Run in the same ROOT/EIC environment used for the build, from the repository root:

```sh
python3 tests/smoke/run.py --build-dir NewStructure/build
```

For an in-source CMake build, use `--build-dir NewStructure`. No extra CMake option
is needed. Each command has a 30-second limit; `--timeout 60` changes that limit.
Any required missing artifact, failing command, timeout, or wrong numerical/data
result returns a nonzero exit status. All fixture output is temporary and removed
on success or failure. The suite does not silently skip a required check.

### Checks in the baseline

1. The explicitly selected `Convert` and `DataPrep` executables exist and actually
   start with `-h`, return zero, and print their usage text. This exercises startup
   and shared-library discovery, not a detector conversion.
2. `root-config --version` runs. ROOT then explicitly loads the selected
   `libLFHCAL` with its generated dictionary artifacts. No ROOT startup macros
   or working-directory autoload are relied upon.
3. The real `Calib` implementation calculates a known low-gain scale:
   high-gain scale 120 divided by correlation slope 4 gives 30, with absolute
   tolerance `1e-12`. This is a tiny deterministic numerical control, not a MIP fit.
4. ROOT writes a real `Calib` object and a one-entry `TTree` containing a real
   `Tile`. A second ROOT process reopens the file without recovery, checks the
   object names, entry count and values, and repeats the calibration calculation.

The inputs are generated in code: one channel, one event, no random numbers and
no beam-data dependency. `driver.C` propagates interpreter and payload failures
as nonzero status; the Python runner also requires an explicit success marker.
Checks do not use C++ `assert`, so release builds cannot disable them.

## Optional plotting checks

[Plotting regression and comparison routines](../../NewStructure/tests/FIT_CURVE_TESTS.md)
are separate explicit commands; the default smoke runner does not invoke them.
They require the renderer from PR #16. Pass `--source-dir` to its `NewStructure`
checkout if that feature is not yet in this checkout. Optional adaptive
comparisons additionally require the unchanged `AdaptiveLangau.h` from PR #89.
No detector data, full campaign, or generated evidence is added to the baseline.

## Optional Yall readiness, not a Yall test campaign

If Yall is relevant to this environment, explicitly request only its version:

```sh
python3 tests/smoke/run.py --build-dir NewStructure/build --yall /path/to/yall-run
```

This does **not** validate a Yallfile, create/start a campaign, or contact Condor.
Without `--yall`, the report says Yall readiness was not requested. A shell
function is not an executable: if EIC setup exposes only the `yall-run` function,
run `yall-run --version` separately in that activated shell. The runner does not
source environment files or install another copy of Yall.

## Build-tree versus installed artifacts

The current upstream CMake project has no `install()` rules. Its bootstrap builds
in `NewStructure/build`; that is a post-build check, not proof of a relocatable
installation. This suite does not introduce or claim a new install layout.

For an existing separately deployed layout, point at the actual artifacts rather
than falling back to build-tree binaries:

```sh
python3 tests/smoke/run.py --bin-dir /deployment/bin \
  --library /deployment/lib/libLFHCAL.so
```

The library's directory must also contain nonempty `libLFHCAL_rdict.pcm` and
`libLFHCAL.rootmap`. Use the test checkout matching those artifacts, because the
ROOT payload includes its `NewStructure` class headers. This is not a standalone
binary-only package or a test that build-tree headers are absent. The runner
prints the selected binary/library/ROOT paths and does not change
`LD_LIBRARY_PATH`. Within ROOT it adds the selected library directory to the
dictionary autoload path. Activate the intended runtime environment first. `--root` and
`--root-config` can select exact matching ROOT executables when needed.

## Provenance and boundaries

The readiness checks are consolidated from the actual upstream
`tools/bootstrap-yall-integration.sh`: ROOT version, executable presence and
optional Yall availability. Here executable presence is strengthened to startup.
The write/read pattern follows the existing `NewStructure/Tests/dummy.cc` and
`dummyRead.cc` examples, but uses **current production classes**, checks the
results, and does not reuse their committed binaries or old `Dummy.root` file.
The numerical and checked production-object fixture are new coverage.

Existing `tools/tests` tests exercise bootstrap/environment script behavior and
remain separate. Existing `examples/yall/check_shared_conversions.py` checks
campaign graphs; it is deliberately not in this baseline. This change does not
modify the bootstrap or make tests run automatically during installation.

Useful later additions, outside this small baseline:

- Promote the strict raw-conversion diagnostics only after decoder defects are fixed.
- A known calibration text fixture loaded through the public file reader.
- A reference histogram fit with documented numerical tolerances.
- Bad input and unwritable output checks with reliable nonzero process status.
- The HGCROC decoder's readiness, when a decoder-enabled installation is required.

## Maintainer checks of the runner

```sh
python3 -m unittest discover -s tests/smoke -p 'test_*.py' -v
python3 -m unittest discover -s tools/tests -v
```

The first command uses fake executables to test failure propagation, timeouts,
path quoting, temporary-directory cleanup and optional-Yall behavior. It also
checks real fixture hashes and raw record structure without ROOT. Passing it
is **not** evidence that the production ROOT smoke checks passed. Run the real
one-command check in a compiled LFHCal environment as well.

## GitHub Actions

`ROOT smoke tests` builds `Convert` and `DataPrep` and runs the runner unit tests
and real ROOT smoke checks on GitHub-hosted Ubuntu 24.04. It uses the official
`rootproject/root:6.34.00-ubuntu24.04` image pinned by digest, with read-only
repository permissions and the decoder revision recorded in the submodule.
It runs for relevant pull-request changes, pushes to main, or manual dispatch.
The plotting regression runs only when its renderer is in the tested checkout;
otherwise it explicitly reports a skip. No other branch is fetched, no beam
campaign is started, and the separate `Yall examples` result is not a ROOT pass.

## Optional strict raw conversion (known failing)

See [RAW_CONVERSION.md](RAW_CONVERSION.md) for synthetic and small real CAEN
checks. The [real fixture provenance](fixtures/caen/README.md) distinguishes
acquisition-quality concerns from deliberately corrupted records. These opt-in
commands currently fail and are not run by the baseline smoke command or CI
gate. Offline tests verify fixture bytes/structure only; they do not validate
production conversion.
