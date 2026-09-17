# BNL yall-integration setup

Run this from your **normal BNL login/submit shell**, outside `eic-shell` or a
Python virtual environment. It uses the Python and Condor already provided by
BNL. ROOT and the LFHCal build tools come from `eic-shell`.

Choose a workspace, enter it, and run the installer. **The current directory
is the installation root**; no extra `eic-2026` directory is added.

```tcsh
mkdir my_eic_work_with_LFHCAL
cd my_eic_work_with_LFHCAL
curl -fsSL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration/tools/bootstrap-yall-integration.sh | bash
```

These commands also work from bash. The installer runs as a bash subprocess;
it does not replace your login shell or enter an interactive container.
To inspect it first, download the same URL with `curl -fsSL -o
bootstrap-yall-integration.sh`, review it, and run
`bash bootstrap-yall-integration.sh` from the workspace.

The bootstrap script:

- installs `eic-shell` using the official `https://get.epic-eic.org` installer;
- clones or updates `paulnord/yall-run` on `main`;
- installs it with `python3 -m pip install --user -e <workspace>/yall-run`;
- clones or updates LFHCal on `yall-integration`, including submodules;
- configures and builds `NewStructure` inside `eic-shell`;
- checks `Convert`, `DataPrep`, ROOT and the host-side runner; and
- writes bash/tcsh environment files and creates data/work directories.

There is **no virtual environment**, Python installation, Condor installation,
or pip upgrade. The editable user installation points to the `yall-run` source
in this workspace. Its command normally lives in `~/.local/bin`; the generated
environment files add the actual Python user-bin directory to `PATH`.
This is one user installation for that host Python, not a separate runner per
workspace: installing from another checkout switches the user installation to
that checkout.

The resulting layout is:

```text
my_eic_work_with_LFHCAL/
    eic-shell
    yall-run/
    epic-lfhcal-tbana/
    activate.sh
    activate.tcsh
    site-env.sh
    site-env.tcsh
    data/TB2026/
    work/
```

The official EIC installer may create additional environment files/directories
under this root. Raw data are not automatically downloaded, and no campaigns
are created or submitted by the bootstrap.

To select a destination explicitly instead of the current folder:

```tcsh
curl -fsSL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration/tools/bootstrap-yall-integration.sh \
  | bash -s -- --prefix /path/to/my_eic_work_with_LFHCAL
```

Relative prefixes are resolved against the installer's starting directory.
An inherited `LFHCAL_HOME` does not redirect installation.

## Data and work directories

Edit `site-env.tcsh` (or `site-env.sh` for bash) in the workspace to choose your
storage paths. The installer preserves these files on later runs. Defaults:

```text
LFHCAL_DATA=<workspace>/data/TB2026
LFHCAL_WORK=<workspace>/work
```

`LFHCAL_DATA` holds imported raw `Run<run>.h2g` files. `LFHCAL_WORK` is the
common root for analysis products. Each production Yallfile appends its own
example name, so do not also append that name to the common work root.
Explicit storage environment variables override the generated defaults.

For batch work, choose shared storage visible to the worker nodes for the
installation, raw data, work area and campaign records. Set your own permitted
BNL storage paths, not another user's STAR/GPFS directory.

## Fresh terminal and example setup

From the workspace, enter the example and source its environment file:

```tcsh
cd epic-lfhcal-tbana/examples/yall/fullset-f2-repro
source env.tcsh
yall-run validate
yall-run plan
```

For bash, use `source env.sh` instead. The example discovers the installation
in the checkout's parent directory, loads its environment, prepares the example
work directory and prints the paths. No top-level activation is required first.

**Stay in the normal login shell to create, start and inspect Condor campaigns.**
The Condor Yallfile wraps the scientific commands in `eic-shell` automatically;
Python, Yall and Condor remain on the host.

The top-level `activate.tcsh` and `activate.sh` are simply path/storage setup
scripts, not virtual-environment activation. They can also be sourced directly:

```tcsh
source /path/to/my_eic_work_with_LFHCAL/activate.tcsh
```

They set `LFHCAL_HOME`, `LFHCAL_REPO`, `YALL_RUN_REPO`, `EIC_SHELL` and the
storage variables, add the user-bin directory to `PATH`, and do not change the
current directory. The tcsh version also runs `rehash`.

For a checkout outside the workspace, set `LFHCAL_HOME` to an existing
installation before sourcing the example environment. A local workspace
activation file takes precedence over that fallback.

## Updating

Enter the existing workspace before rerunning the installer, or use `--prefix`.
Existing site files and products are retained. Avoid updating or rebuilding the
shared checkout while jobs are using it. Use a fresh work root for a new
production analysis; a new campaign ID alone does not make output paths unique.

When replacing an earlier virtual-environment-based installation, rerun from a
fresh normal BNL terminal. The installer rewrites the activation files for the
user installation but does not delete the old `.venv-yall` directory or alter
already-created campaigns.

Installation paths are recorded as absolute paths in generated files and build
products. Moving an already installed workspace or frozen campaign is not
supported by these setup scripts.
