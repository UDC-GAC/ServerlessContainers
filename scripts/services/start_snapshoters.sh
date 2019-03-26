#!/usr/bin/env bash
tmux new -d -s "Refeeder" "python3 Refeeder/Refeeder.py"
tmux new -d -s "DatabaseSnapshoter" "python3 Snapshoters/DatabaseSnapshoter.py"
tmux new -d -s "StructuresSnapshoter" "python3 Snapshoters/StructuresSnapshoter.py"

