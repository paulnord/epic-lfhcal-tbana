# Source this helper from an examples/yall/<example>/env.tcsh wrapper.
# It activates the installed yall/LFHCal environment and prepares the shared
# raw-data and work directories used by the Yallfile.

if ($#argv < 1) then
    echo "example-env.tcsh: missing example name"
    goto lfhcal_env_done
endif

set _example = "$argv[1]"

if (! $?LFHCAL_HOME) then
    setenv LFHCAL_HOME "$HOME/eic-2026"
endif

if (! -f "$LFHCAL_HOME/activate.tcsh") then
    echo "LFHCal environment not installed at $LFHCAL_HOME."
    echo "Run tools/bootstrap-yall-integration.sh first."
    goto lfhcal_env_done
endif

source "$LFHCAL_HOME/activate.tcsh"

setenv LFHCAL_EXAMPLE "$_example"
setenv LFHCAL_EXAMPLE_WORK "$LFHCAL_WORK/$_example"

mkdir -p "$LFHCAL_DATA" "$LFHCAL_EXAMPLE_WORK" "$LFHCAL_WORK/campaigns"

echo "LFHCAL_DATA=$LFHCAL_DATA"
echo "LFHCAL_WORK=$LFHCAL_WORK"
echo "EIC_SHELL=$EIC_SHELL"
echo "Example work=$LFHCAL_EXAMPLE_WORK"

unset _example

lfhcal_env_done:
