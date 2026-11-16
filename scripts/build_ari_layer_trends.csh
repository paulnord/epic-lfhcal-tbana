#!/bin/tcsh -f
# Invoke from repository root after enabling the site's ROOT environment.
if (! -e NewStructure/AriLayerTrends.cc) then
  echo "Run this script from the repository root."
  exit 1
endif
which root-config >& /dev/null
if ($status != 0) then
  echo "Enable ROOT first (site setup or source thisroot.csh)."
  exit 1
endif
mkdir -p local-build
# Follow ROOT's configured C++ standard; source requires C++17 or newer.
c++ -O2 `root-config --cflags` NewStructure/AriLayerTrends.cc `root-config --libs` -o local-build/AriLayerTrends
if ($status != 0) exit 1
./local-build/AriLayerTrends --self-test
exit $status
