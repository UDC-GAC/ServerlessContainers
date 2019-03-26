#!/usr/bin/env bash
DEV_PATH=$HOME/development/bdwatchdog
export RESCALER_PATH=$DEV_PATH/AutomaticRescaler

echo "Setting container resources"
bash $RESCALER_PATH/src/NodeRescaler/config/small-limit/update_all.sh &> /dev/null

echo "Resetting host resources accounting"
python3 $RESCALER_PATH/src/StateDatabase/initializers/reset_host_structure_info.py
