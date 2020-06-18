#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
export PYTHONPATH=$scriptDir

export BDWATCHDOG_PATH=$scriptDir/../bdwatchdog/
export RESCALING_PATH=$scriptDir
export PYTHONPATH=$BDWATCHDOG_PATH:$RESCALING_PATH


