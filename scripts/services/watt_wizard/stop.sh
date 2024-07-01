#!/usr/bin/env bash
tmux kill-session -t "watt_wizard"
#kill $(ps aux | grep "[g]unicorn3 --bind 0.0.0.0:7777" | awk '{print $2}')