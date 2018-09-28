#!/usr/bin/fish
set -g DEV_PATH $HOME/development
set -g RESCALER_PATH $DEV_PATH/automatic-rescaler
set -g BDWACHDOG_PATH $DEV_PATH/metrics-to-time-series
set -g APPLICATION_TIMESTAMPS_PATH $DEV_PATH/applications-timestamps-snitch
export PYTHONPATH=$RESCALER_PATH:$BDWACHDOG_PATH:$APPLICATION_TIMESTAMPS_PATH
