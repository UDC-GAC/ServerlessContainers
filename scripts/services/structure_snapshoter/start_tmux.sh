#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

tmux new -d -s "structure_snapshoter" "bash $scriptDir/start.sh"
