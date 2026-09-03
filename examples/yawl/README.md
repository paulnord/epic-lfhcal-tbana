# Yawl examples

These examples show how to run existing LFHCal executables with `yawl-run` without adding provenance code to the C++ applications.

They assume:

- LFHCal has been built in `NewStructure/build`.
- `yawl-run` is installed and on `PATH`.
- Example input filenames have been replaced with real ROOT files, or suitable symlinks have been created.

Start with `hgcroc-study`, then compare it with the Condor version. `calibration-pair` demonstrates a simple dependency between pedestal extraction and MIP calibration.

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

The examples use `-L 1000` for quick smoke tests. Remove that limit for production processing.

The Condor example assumes the executable, input data, campaign directory, and runtime environment are visible on worker nodes. A site/container `%wrapper` can be added when that environment is standardized.
