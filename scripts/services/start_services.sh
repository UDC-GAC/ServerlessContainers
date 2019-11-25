#!/usr/bin/env bash
tmux new -d -s "Guardian" "source set_pythonpath.sh; python3 src/Guardian/Guardian.py"
tmux new -d -s "Scaler" "source set_pythonpath.sh; python3 src/Rescaler/ClusterScaler.py"
tmux new -d -s "Refeeder" "source set_pythonpath.sh; python3 src/Refeeder/Refeeder.py"
tmux new -d -s "DatabaseSnapshoter" "source set_pythonpath.sh; python3 src/Snapshoters/DatabaseSnapshoter.py"
tmux new -d -s "StructuresSnapshoter" "source set_pythonpath.sh; python3 src/Snapshoters/StructuresSnapshoter.py"
tmux new -d -s "Orchestrator" "source set_pythonpath.sh; cd src/Orchestrator; gunicorn3 --bind 0.0.0.0:5000 wsgi:app -w 2 --threads 2"
tmux new -d -s "SanityChecker" "source set_pythonpath.sh; python3 src/SanityChecker/SanityChecker.py"
