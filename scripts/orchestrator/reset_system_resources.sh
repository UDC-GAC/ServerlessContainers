#!/usr/bin/env bash
export RESCALER_PATH=$HOME/development/AutomaticRescaler

echo "Setting container resources"
bash $RESCALER_PATH/src/NodeRescaler/config/small-limit/update_all.sh &> /dev/null

echo "Resetting host resources accounting"
python3 $RESCALER_PATH/src/StateDatabase/initializers/reset_host_structure_info.py
