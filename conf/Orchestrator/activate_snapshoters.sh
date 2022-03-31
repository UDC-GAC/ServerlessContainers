#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

echo "Activate DatabaseSnapshoter and StructuresSnapshoter services"
bash $ORCHESTRATOR_PATH/DatabaseSnapshoter/activate.sh
bash $ORCHESTRATOR_PATH/StructuresSnapshoter/activate.sh