#!/usr/bin/env bash
kill $(ps aux | grep "[g]unicorn3" | grep "wsgi:node_rescaler" | awk '{print $2}')
tmux kill-session -t "NodeRescaler"
