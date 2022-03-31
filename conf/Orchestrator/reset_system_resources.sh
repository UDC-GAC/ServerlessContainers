#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
export LXD_SCRIPT_PATH=${scriptDir}/../NodeRescaler/
export CONF_SCRIPTS_PATH=${scriptDir}/../StateDatabase/
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator


echo "Deactivate Guardian and Scaler services"
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh

echo "Setting container resources in LXD"
bash ${LXD_SCRIPT_PATH}/update_all.sh
sleep 2

echo "Resetting host resources accounting in CouchDB"
python3 ${CONF_SCRIPTS_PATH}/reset_host_structure_info.py
sleep 2

echo "Activate Guardian and Scaler services again"
bash $ORCHESTRATOR_PATH/Guardian/activate.sh
bash $ORCHESTRATOR_PATH/Scaler/activate.sh