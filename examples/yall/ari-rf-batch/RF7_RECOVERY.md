# Recover missing RF7 signal run 331

Run `recover_rf7.py` with the host Python, outside an interactive EIC shell.
It checks nonempty readable `Run330.h2g` and `Run331.h2g`, the EIC launcher,
Git, yall-run, and Condor commands before preparing anything. Existing yall-run
must meet the version requirements in README.md.

Default raw directory: `/gpfs01/star/pwg/pnord/eic/2026TBdata/raw`.
Default persistent parent: `/gpfs01/star/pwg/pnord/eic/2026TBdata/analyzed`.
Default launcher: `/star/u/pnord/bin/eic-shell`.
Override these with `--raw`, `--parent`, or `--eic-shell` if necessary.

The helper clones a fresh source checkout pinned to
`639f59189347169f7c357b784cd99a5fd9922801`, checks its SHA, initializes submodules,
and prepares only `(pedestal=330, signal=331, ToA scan=2)` using the existing
calibration recipe. The original batch table and previously analyzed runs are
unchanged. The generated 13-node graph covers a worker build/tests, two raw
conversions, pedestal, transfer, MIP, selection, three refinements, calibration,
waveform and single-run summary. No heavy processing runs on the login host.

Without `--submit`, it validates and prints the plan and tcsh submission commands.
With `--submit`, it creates and starts the Condor campaign once, and prints status.
The full source, work, products and campaign are within a new `ari-rf7-*`
subdirectory of the persistent parent. Never move it while a job is running.
Preparation and submission are not proof of completion or scientific validation.

After completion, verify calibrated events and waveform histograms, then use the
plot-only workflow to add run 331 to the combined plots and books. This helper
does not update old book manifests or generate annotated measurement CSVs itself.

Any failure retains the workspace for inspection. Do not rerun blindly after an
uncertain scheduler submission; inspect the recorded `work/campaign-path.txt`.
Source preparation requires the repository calibration recipe described in README;
it does not establish that any historical manual calibration overrides are needed.

Validation: six mocked workflow tests plus a synthetic real-helper preparation
check; no BNL raw-data processing or scheduler execution is claimed.

```sh
python3 -m unittest discover -s examples/yall/ari-rf-batch -p test_recover_rf7.py -v
```
