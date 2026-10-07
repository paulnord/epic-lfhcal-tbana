# PS full-chain run: Legacy with PR86 and PR87 fixes

Use a fresh checkout of the published `codex/adaptive-langau-minimal` branch.
The inspected source already contains the vector/array and temporary-buffer
fixes from PR86, the checked I/O/exit-status fixes from PR87, and the direct
Legacy HG fitter with the original range selection. It does not dispatch to
AdaptiveMipFit or enable the valley boundary.

This full run uses the existing `examples/yall/ps-*/Yallfile` recipes. Unlike
`Yallfile.legacy`, it starts with raw conversion and pedestal extraction, so
the Convert changes are exercised too. It then merges muons, transfers
constants, fits MIPs, selects events, runs R1-R5, and copies final constants.
The same run lists, pedestal associations, mapping and ToA choices are retained.

Both executables and their library are built once, outside the Yallfiles.
The build script checks the inspected source blobs, requires the pinned decoder
submodule, and records source/configuration and binary checksums. The launch
script verifies that record, validates/plans all selected Yallfiles, and lets
their existing preflight commands run during campaign creation. There are no
generated Yallfiles, additional runtime wrappers, or compilation batch tasks.

## Build (tcsh)

```tcsh
set REPO = ~/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark
set LEGACY = /gpfs01/star/scratch/pnord/lfhcal/ps-legacy-pr86-pr87-20261007
setenv LFHCAL_SOURCE "$LEGACY/source"
setenv CALWORK "$LEGACY"
setenv LFHCAL_RAW /gpfs01/star/pwg/pnord/eic
setenv EIC_SHELL ~/my_eic_work_with_LFHCAL/eic-shell

git -C "$REPO" fetch origin codex/adaptive-langau-minimal && \
git -C "$REPO" worktree add --detach "$LFHCAL_SOURCE" FETCH_HEAD && \
git -C "$LFHCAL_SOURCE" submodule update --init --recursive && \
bash "$LFHCAL_SOURCE/examples/yall/calibration-2026/build-legacy-pr86-pr87.sh" "$EIC_SHELL"
```

Wait for `Legacy + PR86 + PR87 build ready`. If the build fails, fix the
reported problem and rerun just the last `bash` command. Reuse of a successful
build checks its hashes and does not recompile. Keep the source/build fixed
while these jobs run. The previous adaptive work directory is untouched.

## Launch and inspect (tcsh)

```tcsh
bash "$LFHCAL_SOURCE/examples/yall/calibration-2026/launch-ps-legacy-pr86-pr87.sh"
```

By default this submits all 17 PS sets. Pass names such as `ps-b1 ps-i2` after
the script path to run a subset. Plans are saved in `$CALWORK/plans`; the
campaign list is `$CALWORK/ps-campaigns.txt`. The fresh full run can require
roughly 350 GB, based on the completed adaptive batch.

Creation or submission failure stops the loop. Rerunning the launcher reuses
recorded campaigns and skips those already submitted; it does not restart
failed jobs or create duplicate submissions. Use normal yall-run recovery
commands for an already-submitted campaign. A directory left by a failed
`create` is not treated as a successful campaign.

```tcsh
foreach marker ( "$CALWORK"/launch-state/*.campaign )
    set cam = `cat "$marker"`
    yall-run status "$cam" -v
end
```

The fitter is established by the verified source and compiled binary, not just
the `legacy-original` campaign label. Record files are in
`$LFHCAL_SOURCE/NewStructure/build/legacy-pr86-pr87-*`.

The prior adaptive results remain the comparison sample. This legacy run
exercises both fixes on real data; comparing legacy versus adaptive results
does not isolate the memory fix's numerical effect. The separate PR86 local
before/after fit and leak tests remain part of its validation evidence.
