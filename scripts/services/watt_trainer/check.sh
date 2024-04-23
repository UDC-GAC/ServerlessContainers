#!/usr/bin/env bash

tmux has-session -t "watt_trainer" 2>/dev/null
if [ $? != 0 ]; then
  echo "Service 'watt_trainer' IS NOT running"
else
  echo "Service 'watt_trainer' IS running"
fi