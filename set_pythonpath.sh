#!/usr/bin/env bash
thisDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

export BDWATCHDOG_PATH=$thisDir/../BDWatchdog/
export SERVERLESS_PATH=$thisDir
export PYTHONPATH=$BDWATCHDOG_PATH:$SERVERLESS_PATH


