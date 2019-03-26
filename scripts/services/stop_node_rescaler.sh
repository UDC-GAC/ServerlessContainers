#!/usr/bin/env bash
tmux kill-session -t "NodeRescaler"
kill $(ps aux | grep "[g]unicorn3 --bind 0.0.0.0:8000" | awk '{print $2}')