#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

echo "Activating Guardian"
bash $ORCHESTRATOR_PATH/Guardian/activate.sh

echo "Activating Scaler"
bash $ORCHESTRATOR_PATH/Scaler/activate.sh

#echo "Activating Structures Snapshoter"
#bash $ORCHESTRATOR_PATH/StructuresSnapshoter/activate.sh
#
#echo "Activating Database Snapshoter"
#bash $ORCHESTRATOR_PATH/DatabaseSnapshoter/activate.sh