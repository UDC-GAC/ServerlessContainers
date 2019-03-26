#!/usr/bin/env bash
tmux new -d -s "NodeRescaler" "cd src/NodeRescaler; gunicorn3 --bind 0.0.0.0:8000 wsgi:app -w 2 --threads 2"
