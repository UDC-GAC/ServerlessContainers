#!/usr/bin/env fish

set -l thisDir (realpath (dirname (status -f)))
export PYTHONPATH=$thisDir

export BDWATCHDOG_PATH=$thisDir/../BDWatchdog/
export SERVERLESS_PATH=$thisDir
export PYTHONPATH=$BDWATCHDOG_PATH:$SERVERLESS_PATH
