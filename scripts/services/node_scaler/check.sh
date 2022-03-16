#!/usr/bin/env bash

tmux has-session -t "node_scaler" 2>/dev/null
if [ $? != 0 ]; then
  echo "Service 'node_scaler' IS NOT running"
else
  echo "Service 'node_scaler' IS running"
fi
