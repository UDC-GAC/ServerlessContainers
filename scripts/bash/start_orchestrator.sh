#!/usr/bin/env bash
#tmux new -d -s "Orchestrator" "source set_pythonpath.sh && cd $RESCALER_PATH/Orchestrator && gunicorn --bind 0.0.0.0:5000 wsgi:app -w 2"
tmux new -d -s "Orchestrator" "source set_pythonpath.sh && python Orchestrator/Orchestrator.py &> orchestrator.log"
