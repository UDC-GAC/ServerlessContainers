#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

tmux new -d -s "guardian" "bash $scriptDir/start.sh"
