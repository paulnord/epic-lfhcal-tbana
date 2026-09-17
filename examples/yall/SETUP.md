# One-command yall-integration setup

The `yall-integration` branch can install its complete runnable environment under one directory. The default is `~/eic-2026`.

```bash
curl -fsSL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration/tools/bootstrap-yall-integration.sh | bash
```

The bootstrap script:

- installs `eic-shell` using the official `https://get.epic-eic.org` installer;
- clones or updates `paulnord/yall-run` on `main`;
- installs `yall-run` into `~/eic-2026/.venv-yall`;
- clones or updates `paulnord/epic-lfhcal-tbana` on `yall-integration`;
- configures and builds `NewStructure` inside `eic-shell`;
- checks for the `Convert` and `DataPrep` executables;
- writes bash and tcsh activation files; and
- creates default raw-data and work directories.

Use another installation root by setting `LFHCAL_HOME` for the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration/tools/bootstrap-yall-integration.sh \
  | LFHCAL_HOME=/path/to/eic-2026 bash
```

## Site storage

The installer creates these local configuration files and does not overwrite them on later runs:

```text
~/eic-2026/site-env.sh
~/eic-2026/site-env.tcsh
```

Their defaults are:

```text
LFHCAL_DATA=~/eic-2026/data/TB2026
LFHCAL_WORK=~/eic-2026/work
```

`LFHCAL_DATA` is the directory into which raw `Run<run>.h2g` files are imported. `LFHCAL_WORK` is the common writable root for campaign products. On a batch site, edit the site file once to use shared/scratch storage visible to worker nodes.

## Fresh terminal

For tcsh:

```tcsh
source ~/eic-2026/activate.tcsh
```

For bash:

```bash
source ~/eic-2026/activate.sh
```

The activation file sets `LFHCAL_HOME`, `LFHCAL_REPO`, `YALL_RUN_REPO`, `EIC_SHELL`, puts the host-side yall virtual environment on `PATH`, and loads the site storage configuration.

## Example environments

Each LFHCal Yall example has `env.tcsh` and `env.sh`. Enter the example directory and source the matching file. It activates the common installation, prepares the raw-data directory, prepares the example work directory, and prints the effective paths.

For example, on tcsh:

```tcsh
cd ~/eic-2026/epic-lfhcal-tbana/examples/yall/fullset-f2-repro
source env.tcsh
yall-run validate
yall-run plan
```

The corresponding bash form is:

```bash
cd ~/eic-2026/epic-lfhcal-tbana/examples/yall/fullset-f2-repro
source env.sh
yall-run validate
yall-run plan
```

The production Yallfiles continue to use the common `LFHCAL_WORK` root and create their own named subdirectories beneath it, for example `LFHCAL_WORK/fullset-f2-repro`.
