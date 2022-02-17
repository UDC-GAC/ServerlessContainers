#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

tmux new -d -s "refeeder" "bash $scriptDir/start.sh"

