#!/usr/bin/env bash
tmux kill-session -t "Guardian"
tmux kill-session -t "Scaler"
tmux kill-session -t "Refeeder"
tmux kill-session -t "DatabaseSnapshoter"
tmux kill-session -t "StructuresSnapshoter"
tmux kill-session -t "Orchestrator"
tmux kill-session -t "SanityChecker"
kill $(ps aux | grep "[g]unicorn3 --bind 0.0.0.0:5000" | awk '{print $2}')


