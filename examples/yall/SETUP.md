# One-command yall-integration setup

Choose a workspace, enter it, and run the installer. **The current directory
is the installation root**; no extra `eic-2026` directory is added.

```bash
mkdir my_eic_work_with_LFHCAL
cd my_eic_work_with_LFHCAL
curl -fsSL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration/tools/bootstrap-yall-integration.sh | bash
```

These three commands also work from a tcsh terminal: the installer itself runs
under bash. To inspect the script before executing it, download it with
`curl -fsSL -o bootstrap-yall-integration.sh` followed by the same URL, review
it, and run `bash bootstrap-yall-integration.sh` from the chosen workspace.

The bootstrap script:

- installs `eic-shell` using the official `https://get.epic-eic.org` installer;
- clones or updates `paulnord/yall-run` on `main`;
- installs `yall-run` into the workspace's `.venv-yall`;
- clones or updates `paulnord/epic-lfhcal-tbana` on `yall-integration`, including submodules;
- configures and builds `NewStructure` inside `eic-shell`;
- checks for the `Convert` and `DataPrep` executables;
- writes bash and tcsh activation files; and
- creates default raw-data and work directories.

The resulting layout is:

```text
my_eic_work_with_LFHCAL/
    eic-shell
    yall-run/
    epic-lfhcal-tbana/
    .venv-yall/
    activate.sh
    activate.tcsh
    site-env.sh
    site-env.tcsh
    data/TB2026/
    work/
```

The official EIC installer may create additional environment files/directories
under this root. Raw test-beam data are not automatically downloaded, and no
campaigns are created or submitted by the bootstrap.

To install somewhere other than the current directory, explicitly pass a
prefix (this syntax also works from tcsh):

```bash
curl -fsSL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration/tools/bootstrap-yall-integration.sh \
  | bash -s -- --prefix /path/to/my_eic_work_with_LFHCAL
```

Relative prefixes are resolved against the directory in which the installer
starts. `LFHCAL_HOME` is set by activation; it no longer selects the installer
destination. Thus an older active environment cannot silently redirect a new
installation to its directory. This replaces the former `LFHCAL_HOME=... bash`
installer override.

## Site storage

The installer creates `site-env.sh` and `site-env.tcsh` in the workspace and
does not overwrite them on later runs. Edit the file for the shell you use
(or both files when using both shells).

Their defaults are:

```text
LFHCAL_DATA=<workspace>/data/TB2026
LFHCAL_WORK=<workspace>/work
```

`LFHCAL_DATA` is the directory into which raw `Run<run>.h2g` files are imported.
`LFHCAL_WORK` is the common writable root for campaign products. Explicit
storage environment variables override the generated defaults. On a batch
site, use shared storage visible to worker nodes for the installation,
campaign records and products; the raw-data directory must also be visible.

## Fresh terminal

From your workspace, for tcsh:

```tcsh
source ./activate.tcsh
```

For bash:

```bash
source ./activate.sh
```

Or source the activation file by its full path from another directory.
Activation sets `LFHCAL_HOME`, `LFHCAL_REPO`, `YALL_RUN_REPO`, `EIC_SHELL`, puts
the host-side yall virtual environment on `PATH`, and loads the site storage
configuration. It does not change your current directory.

## Example environments

Each LFHCal Yall example has `env.tcsh` and `env.sh`. Enter the example
directory and source the matching file. It finds the installation in the
checkout's parent directory, activates it, prepares the data and example work
directories, and prints the effective paths. There is no fixed home-directory
assumption, and you do not need to source the top-level activation first.

From your workspace, on tcsh:

```tcsh
cd epic-lfhcal-tbana/examples/yall/fullset-f2-repro
source env.tcsh
yall-run validate
yall-run plan
```

The corresponding bash form is:

```bash
cd epic-lfhcal-tbana/examples/yall/fullset-f2-repro
source env.sh
yall-run validate
yall-run plan
```

For a checkout located outside the installed workspace, set `LFHCAL_HOME` to
an existing installation before sourcing the example environment. A local
workspace activation file takes precedence over that fallback.

The production Yallfiles use the common `LFHCAL_WORK` root and append their own
named subdirectories, for example `<workspace>/work/fullset-f2-repro`. Choose a
fresh work root when rerunning a production analysis; a new campaign ID alone
does not make its output paths unique.

## Updating an existing installation

Enter the existing workspace before rerunning the installer, or use
`--prefix` with that workspace's path. For an existing `~/eic-2026` installation,
that means `cd ~/eic-2026` first. Existing site configuration files are retained;
this change does not relocate earlier data, products, or campaigns. Avoid
updating or rebuilding the shared checkout while jobs are using it.

Installation paths are recorded as absolute paths in generated files and build
products. Choosing a custom directory is supported; moving an already installed
workspace or frozen campaign is not made safe by this change.
