#!/usr/bin/env bash
tmux new -d -s "Refeeder" "source set_pythonpath.sh; python3 src/Refeeder/Refeeder.py"
tmux new -d -s "DatabaseSnapshoter" "source set_pythonpath.sh; python3 src/Snapshoters/DatabaseSnapshoter.py"
tmux new -d -s "StructuresSnapshoter" "source set_pythonpath.sh; python3 src/Snapshoters/StructuresSnapshoter.py"

