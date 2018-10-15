#!/usr/bin/env bash
tmux new -d -s "Guardian" "source set_pythonpath.sh && python Guardian/Guardian.py"
tmux new -d -s "Scaler" "source set_pythonpath.sh && python Rescaler/ClusterScaler.py"
