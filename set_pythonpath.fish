#!/usr/bin/env fish

set -l thisDir (realpath (dirname (status -f)))

if test -z "$BDWATCHDOG_PATH"
    set -gx BDWATCHDOG_PATH $thisDir/../BDWatchdog/
end
export SERVERLESS_PATH=$thisDir
export PYTHONPATH=$BDWATCHDOG_PATH:$SERVERLESS_PATH
