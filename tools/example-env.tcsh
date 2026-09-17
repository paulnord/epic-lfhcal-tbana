# Source this helper from an examples/yall/<example>/env.tcsh wrapper.
# Enter the example directory before sourcing its env.tcsh file.
# It activates the installed yall/LFHCal environment and prepares the shared
# raw-data and work directories used by the Yallfile.

if ($#argv < 1) then
    echo "example-env.tcsh: missing example name"
    goto lfhcal_env_done
endif

set _example = "$argv[1]"

# The wrapper is sourced from <workspace>/<repo>/examples/yall/<example>.
# Prefer its workspace to an LFHCAL_HOME left by another installation.
# Keep explicit LFHCAL_HOME as a fallback for a separately located checkout.
set _lfhcal_workspace = "`cd ../../../.. && /bin/pwd -P`"
if (-f "$_lfhcal_workspace/activate.tcsh") then
    unset LFHCAL_HOME
    setenv LFHCAL_HOME "$_lfhcal_workspace"
endif

if (! $?LFHCAL_HOME) then
    echo "LFHCal environment not installed at $_lfhcal_workspace."
    echo "Run the bootstrap from your workspace, or set LFHCAL_HOME to an existing installation."
    goto lfhcal_env_done
endif

if (! -f "$LFHCAL_HOME/activate.tcsh") then
    echo "LFHCal environment not installed at $LFHCAL_HOME."
    echo "Run the bootstrap from your workspace first."
    goto lfhcal_env_done
endif

source "$LFHCAL_HOME/activate.tcsh"
if ($status != 0) goto lfhcal_env_done

setenv LFHCAL_EXAMPLE "$_example"
setenv LFHCAL_EXAMPLE_WORK "$LFHCAL_WORK/$_example"

mkdir -p "$LFHCAL_DATA" "$LFHCAL_EXAMPLE_WORK" "$LFHCAL_WORK/campaigns"
if ($status != 0) goto lfhcal_env_done

echo "LFHCAL_HOME=$LFHCAL_HOME"
echo "LFHCAL_DATA=$LFHCAL_DATA"
echo "LFHCAL_WORK=$LFHCAL_WORK"
echo "EIC_SHELL=$EIC_SHELL"
echo "Example work=$LFHCAL_EXAMPLE_WORK"

lfhcal_env_done:
unset _example _lfhcal_workspace
