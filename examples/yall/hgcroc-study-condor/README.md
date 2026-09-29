# hgcroc-study Condor example

This directory does **not** ship an `input.root` file. The `Yallfile` expects a pre-existing converted HGCROC ROOT file with that name on storage visible to the submit host, execute node, and EIC container.

For TB2026, **run 298** is a reasonable example. If you already have a converted run 298 file, link or copy it here as `input.root`. A converted file from `../lfhcal-simple` can also be used for workflow testing, although that smoke-test file contains only 1000 events.

Submit this example from the normal host shell, not from inside `eic-shell`; the Yallfile wraps the scientific payload in the configured EIC environment.

`HGCROCStudy -w` performs substantial histogramming and plot production. Even with `-L 1000`, this is not an especially fast smoke test. Use the no-data Condor smoke test in `../SETUP.md` when the goal is only to validate scheduler/container plumbing.

The run number above is an example, not a requirement. Any compatible converted TB2026 HGCROC ROOT file can be supplied as `input.root`.
