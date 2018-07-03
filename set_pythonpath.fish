#!/usr/bin/fish
set -g DEV_PATH $HOME/development
set -g RESCALER_PATH $DEV_PATH/automatic-rescaler
set -g BDWACHDOG_PATH $DEV_PATH/metrics-to-time-series
export PYTHONPATH=$RESCALER_PATH:$BDWACHDOG_PATH
