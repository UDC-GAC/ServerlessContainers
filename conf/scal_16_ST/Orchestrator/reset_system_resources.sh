#!/usr/bin/env bash
export RESCALER_PATH=$HOME/development/ServerlessContainers
export LXD_SCRIPT_PATH=$RESCALER_PATH/conf/scal_16_ST/NodeRescaler/
export COUCHDB_SCRIPT_PATH=$RESCALER_PATH/conf/scal_16_ST/StateDatabase/

curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/scaler/CHECK_CORE_MAP -d '{"value":"false"}'
sleep 10
echo "Setting container resources in LXD"
bash $LXD_SCRIPT_PATH/update_all.sh &> /dev/null

echo "Resetting host resources accounting in CouchDB"
python3 $COUCHDB_SCRIPT_PATH/reset_host_structure_info.py
sleep 10
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/scaler/CHECK_CORE_MAP -d '{"value":"true"}'
