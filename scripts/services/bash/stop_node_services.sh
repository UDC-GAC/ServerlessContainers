#!/usr/bin/env bash
tmux kill-session -t "NodeRescaler"
kill $(ps aux | grep "[g]unicorn --bind 0.0.0.0:8000" | awk '{print $2}')
tmux kill-session -t "SanityChecker"
tmux kill-session -t "Scaler"
tmux kill-session -t "StructuresSnapshoter"

