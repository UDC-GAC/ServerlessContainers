#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../../set_pythonpath.sh"

tmux new -d -s "Guardian" "python3 src/Guardian/Guardian.py"
tmux new -d -s "Scaler" "python3 src/Rescaler/ClusterScaler.py"
tmux new -d -s "Refeeder" "python3 src/Refeeder/Refeeder.py"
tmux new -d -s "DatabaseSnapshoter" "python3 src/Snapshoters/DatabaseSnapshoter.py"
tmux new -d -s "StructuresSnapshoter" "python3 src/Snapshoters/StructuresSnapshoter.py"
tmux new -d -s "Orchestrator" "python3 src/Orchestrator/Orchestrator.py"
tmux new -d -s "SanityChecker" "python3 src/SanityChecker/SanityChecker.py"
