#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

export BDWATCHDOG_PATH=$scriptDir/../BDWatchdog/
export SERVERLESS_PATH=$scriptDir
export PYTHONPATH=$BDWATCHDOG_PATH:$SERVERLESS_PATH


