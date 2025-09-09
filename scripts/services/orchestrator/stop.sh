#!/usr/bin/env bash
tmux kill-session -t "orchestrator"

GUNICORN_DAEMON=$(ps aux | grep "[g]unicorn3 --bind 0.0.0.0:5000" | awk '{print $2}')
if [ -n "${GUNICORN_DAEMON}" ]; then
    kill ${GUNICORN_DAEMON}
fi
