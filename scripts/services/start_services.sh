#!/usr/bin/env bash
tmux new -d -s "Guardian" "python3 src/Guardian/Guardian.py"
tmux new -d -s "Scaler" "python3 src/Rescaler/ClusterScaler.py"
tmux new -d -s "Refeeder" "python3 src/Refeeder/Refeeder.py"
tmux new -d -s "DatabaseSnapshoter" "python3 src/Snapshoters/DatabaseSnapshoter.py"
tmux new -d -s "StructuresSnapshoter" "python3 src/Snapshoters/StructuresSnapshoter.py"
tmux new -d -s "Orchestrator" "cd src/Orchestrator; gunicorn3 --bind 0.0.0.0:5000 wsgi:app -w 2 --threads 2"
tmux new -d -s "SanityChecker" "python3 src/SanityChecker/SanityChecker.py"
