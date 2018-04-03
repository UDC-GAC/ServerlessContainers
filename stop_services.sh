#!/usr/bin/env bash
tmux kill-session -t "Guardian"
tmux kill-session -t "Scaler"
tmux kill-session -t "Refeeder"
tmux kill-session -t "DatabaseSnapshoter"
tmux kill-session -t "NodeSnapshoter"