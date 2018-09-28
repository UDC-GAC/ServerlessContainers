#!/usr/bin/env bash
export DEV_PATH=$HOME/development
export RESCALER_PATH=$DEV_PATH/automatic-rescaler
export BDWACHDOG_PATH=$DEV_PATH/metrics-to-time-series
export APPLICATION_TIMESTAMPS_PATH=$DEV_PATH/applications-timestamps-snitch
export PYTHONPATH=$RESCALER_PATH:$BDWACHDOG_PATH:APPLICATION_TIMESTAMPS_PATH
