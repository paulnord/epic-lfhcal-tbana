# Move, rather than copy, existing Ari products

This is intentionally destructive to the preservation archive layout: selected successful products move to `2026TBdata/analyzed`. Raw data, source/config files, excluded attempts, and archive metadata are not moved. Existing archive verification markers describe the old snapshot; `ARCHIVE_PRODUCTS_MOVED_OR_MOVING` explicitly supersedes any claim that the archive is still intact.

Requires the tested `organize_ari.py` alongside `move_ari.py`. Use Python 3 on Linux. Do not run analysis jobs against source or destination during transfer. No quota-sized duplicate payload is created, although directories and metadata require a little additional space.

The move checks every source checksum before any source removal, refuses cross-filesystem moves, and creates each destination using a no-clobber hard link. It verifies the destination and then unlinks the original name. This portable two-step move avoids rename overwrite races. GPFS fileset rules may reject hard links even on the same filesystem; such a failure stops without removing that source. An interruption between steps leaves two names for the same data, not a duplicate data copy.

From the existing checkout, update this branch (do not build there):

```tcsh
git pull --ff-only origin ari-working-folder-20261116
python3 examples/yall/ari-rf-batch/move_ari.py --archive /gpfs01/star/pwg/pnord/eic/2026TBanalysis/ari-analysis-20261111T163523Z-2189737 --destination /gpfs01/star/pwg/pnord/eic/2026TBdata/analyzed --plan-sha256 fdd85020dc8d7eefff4a718f31df211bf46665a267226ceaf88ceb50fd869563 --accept-archive-incomplete
```

Stop if git pull fails. Destination must not already exist on first execution. Completion is `Move verified:` and `IMPORT_MOVE_VERIFIED`, with no `INCOMPLETE`. RF7/run331 is still absent and needs separate processing. Byte verification is not ROOT structure or scientific validation.

If interrupted, rerun the same Python command with `--resume` appended. It uses the saved move plan, checks all remaining sources and already-moved destinations, and completes only valid states. Do not rerun the original dry-run planner after moving sources; the archive is no longer intact. Do not remove partial destination files or the saved plan. On collisions, tampering, filesystem errors, or unexpected states, stop and inspect rather than override checks.
