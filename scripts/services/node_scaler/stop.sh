#!/usr/bin/env bash

CURRENT_SESSIONS=$(ps aux | grep "wsgi:node_rescaler" | awk '{print $2}')
if [ -n "${CURRENT_SESSIONS}" ]; then
    kill ${CURRENT_SESSIONS}
fi

tmux kill-session -t "node_scaler"
