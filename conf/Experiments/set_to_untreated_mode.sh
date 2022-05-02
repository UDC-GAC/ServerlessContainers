#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

echo "DeActivating Guardian"
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh

echo "DeActivating Scaler"
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh

#echo "DeActivating Structures Snapshoter"
#bash $ORCHESTRATOR_PATH/StructuresSnapshoter/deactivate.sh
#
#echo "DeActivating Database Snapshoter"
#bash $ORCHESTRATOR_PATH/DatabaseSnapshoter/deactivate.sh