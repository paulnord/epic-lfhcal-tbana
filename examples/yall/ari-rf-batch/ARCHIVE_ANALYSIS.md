# Ari preservation handoff (user-run only)

Save the standalone `archive_ari.py` on BNL. Nothing here has been run on BNL. Default operation is read-only inventory. No scheduler submissions, source modifications, deletion or overwriting are implemented.

## 1. Inspect storage at your tcsh prompt

    ls -ld /gpfs01/star/pwg/pnord/eic/2026TBanalysis
    df -h /gpfs01/star/pwg/pnord/eic/2026TBanalysis
    df -i /gpfs01/star/pwg/pnord/eic/2026TBanalysis
    quota -s

Filesystem free space does NOT establish user/group/fileset quota. If quota is unavailable or does not show this PWG allocation, use BNL's supported quota report or ask its administrator before copying.

## 2. Inventory, with no copying

    python3 archive_ari.py

The JSON can be long; inspect or save terminal output without overwriting existing files.

Default trees are the rebuild workspace, latest Run302 annotations workspace and original Run302 workspace. Add verified newer plot/source workspaces with `--source /absolute/path`. Review all `issues`, actual calibrated inputs, campaign status, symlink targets and references before copying. Missing historical references may be nonessential, but must be understood rather than silently dismissed. Manifest paths and command tokens are inventoried; this cannot infer every dependency hidden in arbitrary scripts or relative paths.

## 3. Copy only after reviewing scope, quota and stopping all writers

Choose a NEW directory under the existing PWG analysis parent. The timestamp command below is compatible with tcsh:

    set ARCHIVE = /gpfs01/star/pwg/pnord/eic/2026TBanalysis/ari-analysis-`date -u +%Y%m%dT%H%M%SZ`
    python3 archive_ari.py --copy --destination "$ARCHIVE" --sources-quiescent --quota-reviewed

Repeat any `--source` options from inventory. These flags are your confirmation that writers are stopped and quota was checked, not automated checks. If copying fails, leave the partial directory for inspection and choose a different NEW destination for another attempt. No automatic resume or cleanup is performed.

All files in selected trees are preserved except Git administrative directories (replaced by verified bundles and Git status/diffs) and raw .h2g files (references only). Exact external scratch file dependencies and referenced campaign metadata trees are included. External arbitrary directories and non-scratch files are reported rather than blindly copied. Do not pass a whole home directory. No environment dump is collected. Existing build configuration/logs and source trees are included; external launcher/container dependencies require review.

## 4. Interpret the result carefully

`COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED` means copied files passed SHA256 checks and the recorded source fingerprints stayed unchanged. It does NOT certify scientific validity, complete processing of every run, or full restorability. Absence of this marker means copying/verification did not finish successfully. See `metadata/verified-inventory.json` for original-to-archive mappings and issues, Git bundles, calibrated coverage and raw references.

Symlinks whose targets are included in the payload are rewritten to relative archive targets, with the original link text recorded. Unresolved links retain their original text and are reported. Manifest paths retain their original meaning for provenance, so restoration may require path remapping. Do not execute archived campaigns directly without reviewing paths. No source cleanup is authorized by this workflow.

Raw files already on PWG are recorded with path and stat metadata, without reading huge files again merely to copy analysis. This does not independently verify raw-file integrity; retain or consult existing raw archive checksum records.

Private mode 0700 applies only to the newly created archive root; existing directories' permissions are untouched. Payload files have their original mode/timestamps inside that private root.
