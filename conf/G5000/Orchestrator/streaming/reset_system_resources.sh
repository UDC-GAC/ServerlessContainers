#!/usr/bin/env bash
export RESCALER_PATH=$HOME/development/AutomaticRescaler
export LXD_SCRIPT_PATH=$RESCALER_PATH/conf/G5000/NodeRescaler/streaming
export COUCHDB_SCRIPT_PATH=$RESCALER_PATH/conf/G5000/StateDatabase/streaming

echo "Setting container resources in LXD"
bash $LXD_SCRIPT_PATH/update_all.sh &> /dev/null

echo "Resetting host resources accounting in CouchDB"
python3 $COUCHDB_SCRIPT_PATH/reset_host_structure_info.py