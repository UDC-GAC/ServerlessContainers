#!/usr/bin/env fish

set -l scriptDir (realpath (dirname (status -f)))
export PYTHONPATH=$scriptDir

export BDWATCHDOG_PATH=$scriptDir/../BDWatchdog/
export SERVERLESS_PATH=$scriptDir
export PYTHONPATH=$BDWATCHDOG_PATH:$SERVERLESS_PATH
