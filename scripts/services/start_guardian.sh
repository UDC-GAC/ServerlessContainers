#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../../set_pythonpath.sh"

tmux new -d -s "Guardian" "python3 src/Guardian/Guardian.py"
