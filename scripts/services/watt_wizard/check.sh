#!/usr/bin/env bash

tmux has-session -t "watt_wizard" 2>/dev/null
if [ $? != 0 ]; then
  echo "Service 'watt_wizard' IS NOT running"
else
  echo "Service 'watt_wizard' IS running"
fi