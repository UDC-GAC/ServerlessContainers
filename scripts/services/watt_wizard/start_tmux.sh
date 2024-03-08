#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
tmux new -d -s "watt_wizard" "bash $scriptDir/start.sh"