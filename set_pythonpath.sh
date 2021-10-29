#!/usr/bin/env bash
script_directory=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

export BDWATCHDOG_PATH=$script_directory/../BDWatchdog/
export SERVERLESS_PATH=$script_directory
export PYTHONPATH=$BDWATCHDOG_PATH:$SERVERLESS_PATH


