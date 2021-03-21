#!/usr/bin/env fish

set -l scriptDir (realpath (dirname (status -f)))
export PYTHONPATH=$scriptDir

export BDWATCHDOG_PATH=$scriptDir/../bdwatchdog/
export RESCALING_PATH=$scriptDir
export PYTHONPATH=$BDWATCHDOG_PATH:$RESCALING_PATH
