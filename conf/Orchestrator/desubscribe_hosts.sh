#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

# Host 0
bash $ORCHESTRATOR_PATH/Structures/desubscribe_host.sh host0

# Host 1
bash $ORCHESTRATOR_PATH/Structures/desubscribe_host.sh host1
