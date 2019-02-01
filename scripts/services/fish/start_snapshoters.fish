#!/usr/bin/env bash
tmux new -d -s "Refeeder" "source set_pythonpath.fish; python Refeeder/Refeeder.py"
tmux new -d -s "DatabaseSnapshoter" "source set_pythonpath.fish; python Snapshoters/DatabaseSnapshoter.py"
tmux new -d -s "StructuresSnapshoter" "source set_pythonpath.fish; python Snapshoters/StructuresSnapshoter.py"

