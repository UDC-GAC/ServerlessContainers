#!/usr/bin/env bash
tmux new -d -s "NodeRescaler" "source set_pythonpath.sh && cd $RESCALER_PATH/NodeRescaler && gunicorn --bind 0.0.0.0:8000 wsgi:app -w 2 --threads 2"
#tmux new -d -s "NodeRescaler" "source set_pythonpath.sh && cd $RESCALER_PATH/NodeRescaler && python3.6 NodeRescaler.py &> node_rescaler.log"
