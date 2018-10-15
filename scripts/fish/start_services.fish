#!/usr/bin/env bash
tmux new -d -s "Guardian" "source set_pythonpath.fish; python Guardian/Guardian.py"
tmux new -d -s "Scaler" "source set_pythonpath.fish; python Rescaler/ClusterScaler.py"
