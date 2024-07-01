#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
tmux new -d -s "watt_trainer" "bash $scriptDir/start.sh"