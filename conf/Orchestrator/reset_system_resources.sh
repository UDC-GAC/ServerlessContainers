#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
export LXD_SCRIPT_PATH=${scriptDir}/../NodeRescaler/
export CONF_SCRIPTS_PATH=${scriptDir}/../StateDatabase/
source ${scriptDir}/../../set_pythonpath.sh

echo "Disabling core map checking in the Scaler service"
bash ${SERVERLESS_PATH}/scripts/orchestrator/Scaler/deactivate_core_map_check.sh
sleep 2

echo "Setting container resources in LXD"
bash ${LXD_SCRIPT_PATH}/update_all.sh
sleep 2

echo "Resetting host resources accounting in CouchDB"
python3 ${CONF_SCRIPTS_PATH}/reset_host_structure_info.py
sleep 2

echo "Enabling again core map checking in the Scaler service"
bash ${SERVERLESS_PATH}/scripts/orchestrator/Scaler/activate_core_map_check.sh
