#!/usr/bin/env bash

tmux has-session -t "orchestrator" 2>/dev/null
if [ $? != 0 ]; then
  echo "Service 'orchestrator' IS NOT running"
else
  echo "Service 'orchestrator' IS running"
fi
