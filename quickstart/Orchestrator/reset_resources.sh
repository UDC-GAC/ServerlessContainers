#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../../set_pythonpath.sh"

export LXD_SCRIPT_PATH=$SERVERLESS_PATH/quickstart/NodeRescaler
export COUCHDB_SCRIPT_PATH=$SERVERLESS_PATH/quickstart/StateDatabase

echo "Disabling core map check on the scaler service"
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/scaler/CHECK_CORE_MAP -d '{"value":"false"}'
echo "Deactivating structure snapshoter service"
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/structures_snapshoter/ACTIVE -d '{"value":"false"}'
echo "Deactivating scaler service"
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/scaler/ACTIVE -d '{"value":"false"}'
sleep 15
echo "Setting container resources in LXD"
bash $LXD_SCRIPT_PATH/update_all.sh &> /dev/null

echo "Resetting host resources accounting in CouchDB"
python3 $COUCHDB_SCRIPT_PATH/reset_host_structure_info.py
sleep 15
echo "Enabling core map check on the scaler service"
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/scaler/CHECK_CORE_MAP -d '{"value":"true"}'
echo "Activating structure snapshoter service"
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/scaler/ACTIVE -d '{"value":"true"}'
echo "Activating scaler service"
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/structures_snapshoter/ACTIVE -d '{"value":"true"}'
