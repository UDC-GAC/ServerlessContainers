#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
tmux new -d -s "scaler" "bash $scriptDir/start.sh"
