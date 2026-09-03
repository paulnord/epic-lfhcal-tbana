# Yawl examples

These examples show how to run existing LFHCal executables with `yawl-run` without adding provenance code to the C++ applications.

They assume:

- LFHCal has been built in `NewStructure/build`.
- `yawl-run` is installed and on `PATH`.
- Example input filenames have been replaced with real ROOT files, or suitable symlinks have been created where an example still uses placeholder inputs.

Start with `hgcroc-study`, then compare it with the Condor version. `calibration-pair` demonstrates a simple dependency between pedestal extraction and MIP calibration.

`full-scan` is the end-to-end TB2026 example. It uses current Yawl `@env` and explicit/correlated `@each` bindings so the selected 44 raw runs and 22 pedestal/muon pairs live directly in the Yawlfile. It runs conversion, calibration/refinement, waveform extraction, and the five final comparison products.

From an example directory:

```bash
yawl-run validate
yawl-run plan
yawl-run create
```

Then start the campaign directory printed by `create`:

```bash
yawl-run start campaigns/<campaign-id>
```

The small examples use `-L 1000` for quick smoke tests. Remove that limit for production processing.

The Condor examples assume the executable, input data, campaign directory, and runtime environment are visible on worker nodes. `full-scan` uses the repository's EIC-container `%wrapper`.
