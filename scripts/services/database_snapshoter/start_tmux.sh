#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
tmux new -d -s "database_snapshoter" "bash ${scriptDir}/start.sh"

