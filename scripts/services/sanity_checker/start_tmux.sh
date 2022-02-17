#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

tmux new -d -s "sanity_checker" "bash $scriptDir/start.sh"
