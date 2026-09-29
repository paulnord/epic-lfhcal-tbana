# Source from examples/yall/<example>/env.tcsh in the normal BNL tcsh session.
set _lfhcal_env_rc = 1
if ($#argv < 1) then
    echo "example-env.tcsh: missing example name"
    goto lfhcal_env_done
endif
set _example = "$argv[1]"
set _lfhcal_workspace = "`cd ../../../.. && /bin/pwd -P`"
if (-f "$_lfhcal_workspace/activate.tcsh") then
    unset LFHCAL_HOME
    setenv LFHCAL_HOME "$_lfhcal_workspace"
endif
if (! $?LFHCAL_HOME) then
    echo "Run the bootstrap from your workspace first."
    goto lfhcal_env_done
endif
if (! -f "$LFHCAL_HOME/activate.tcsh") then
    echo "LFHCal environment not installed at $LFHCAL_HOME."
    goto lfhcal_env_done
endif
source "$LFHCAL_HOME/activate.tcsh"
if ($status != 0) goto lfhcal_env_done

setenv LFHCAL_EXAMPLE "$_example"
setenv LFHCAL_EXAMPLE_WORK "$LFHCAL_WORK/$_example"
# Never create directories under LFHCAL_DATA: it is shared input only.
mkdir -p "$LFHCAL_EXAMPLE_WORK" "$LFHCAL_WORK/campaigns"
if ($status != 0) goto lfhcal_env_done

echo "LFHCAL_HOME=$LFHCAL_HOME"
echo "EIC_SHELL=$EIC_SHELL"
echo "Example work=$LFHCAL_EXAMPLE_WORK"
set _lfhcal_env_rc = 0

lfhcal_env_done:
unset _example _lfhcal_workspace
if ($_lfhcal_env_rc != 0) then
    unset _lfhcal_env_rc
    /bin/false
else
    unset _lfhcal_env_rc
    /bin/true
endif
