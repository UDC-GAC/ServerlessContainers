#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

echo "Configuring Guardian"
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh

echo "Configuring Scaler"
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh
bash $ORCHESTRATOR_PATH/Scaler/set_polling_frequency.sh 5
bash $ORCHESTRATOR_PATH/Scaler/set_request_timeout.sh 20

echo "Configuring Structures Snapshoter"
bash $ORCHESTRATOR_PATH/StructuresSnapshoter/deactivate.sh
bash $ORCHESTRATOR_PATH/StructuresSnapshoter/set_polling_frequency.sh 5

echo "Configuring Database Snapshoter"
bash $ORCHESTRATOR_PATH/DatabaseSnapshoter/deactivate.sh
bash $ORCHESTRATOR_PATH/StructuresSnapshoter/set_polling_frequency.sh 5