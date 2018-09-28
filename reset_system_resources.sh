#!/usr/bin/env bash
DEV_PATH=$HOME/development
export RESCALER_PATH=$DEV_PATH/automatic-rescaler

echo "Setting container resources"
bash $RESCALER_PATH/NodeRescaler/config/small-limit/update_all.sh &> /dev/null

echo "Resetting host resources accounting"
python $RESCALER_PATH/StateDatabase/initializers/reset_host_structure_info.py
