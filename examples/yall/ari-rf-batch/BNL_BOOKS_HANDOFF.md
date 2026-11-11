Download/save prepare_ari_books.sh on the BNL login host, then run from tcsh:

/bin/bash prepare_ari_books.sh

No variables need editing. This prepares a fresh workspace at
/gpfs01/star/scratch/pnord/ari-books-20261111 (refuses if it already exists), validates the 23 existing ROOT/CSV pairs, downloads the
pinned source commit, and prints the exact workspace path and separate submission
command. It does NOT submit anything or run ROOT/build/test on the login host.
Run the printed /bin/bash .../submit_books.sh command only after reviewing the plan.

Default output is exactly two 26-page books:
products/AllScans_Unnormalized.pdf (shared scale per layer)
products/AllScans_Normalized.pdf

The one worker builds CombineWaveformBooks and four regression-test targets,
runs the four CTests, and redraws existing profiles and saved measurements.
No events, fitting, calibration, waveform extraction, or measurement changes occur.
Run302 uses the latest verified matching pair from ari-run302-annotations-bdLvhL.

Expected host tools: git, python3, yall-run (0.12.0a7 or newer), configured Condor,
and existing /star/u/pnord/bin/eic-shell. Existing site/Yall accounting defaults
are retained; no account or B.usr group is invented or overridden. The worker uses
the repository's established EIC wrapper and resource policy: 2 CPUs, 4GB memory,
8GB disk, 2h, no automatic retries. The optional decoder is not needed or installed.

The script accepts an explicit fresh absolute destination as argument1 and layer,
robust, or global as argument2. Select one scale per fresh workspace, avoiding
unnecessary duplicate normalized books. Original analysis directories stay read-only.

After products/BOOKS_READY exists, archive the entire printed new workspace along
with the existing rebuild and Run302 workspaces. Pass that exact printed workspace
path as an additional input to your archive command. The preparation script never
writes into the existing input/analysis directories.
