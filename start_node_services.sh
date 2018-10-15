#!/usr/bin/env bash
cd /root/development/automatic-rescaler/
tmux new -d -s "NodeRescaler" "source set_pythonpath.sh && cd $RESCALER_PATH/NodeRescaler && gunicorn --bind 0.0.0.0:8000 wsgi:app -w 4 --threads 2"
tmux new -d -s "SanityChecker" "source set_pythonpath.sh && python SanityChecker/SanityChecker.py"
tmux new -d -s "Scaler" "source set_pythonpath.sh && python Rescaler/ClusterScaler.py"
tmux new -d -s "StructuresSnapshoter" "source set_pythonpath.sh && python Snapshoters/StructuresSnapshoter.py"

