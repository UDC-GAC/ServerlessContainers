#!/usr/bin/env bash
tmux kill-session -t "Orchestrator"
kill $(ps aux | grep "[g]unicorn3 --bind 0.0.0.0:5000" | awk '{print $2}')