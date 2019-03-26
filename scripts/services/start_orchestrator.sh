#!/usr/bin/env bash
tmux new -d -s "Orchestrator" "python3 src/Orchestrator/Orchestrator.py 2> orchestrator.log"
