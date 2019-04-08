#!/usr/bin/env bash
tmux new -d -s "Orchestrator" "source set_pythonpath.sh; python3 src/Orchestrator/Orchestrator.py 2> orchestrator.log"
