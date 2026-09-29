# hgcroc-study local example

This directory does **not** ship an `input.root` file. The `Yallfile` expects a pre-existing converted HGCROC ROOT file with that name.

For TB2026, **run 298** is a reasonable example. If you have already run `../lfhcal-simple`, you can use its converted run as the input, for example from this directory:

```tcsh
ln -s "$LFHCAL_WORK/lfhcal-simple/converted/rawHGCROC_298.root" input.root
```

Then run this local example from inside the EIC environment as described by the surrounding Yall setup documentation.

The workflow limits event processing to 1000 events, but `HGCROCStudy -w` still performs substantial channel-by-channel histogramming and plot production. It can therefore take much longer than the conversion smoke test even with the event limit.

The run number above is an example, not a requirement. Any compatible converted TB2026 HGCROC ROOT file can be supplied as `input.root`.
