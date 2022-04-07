#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

# Host 0 containers
bash $ORCHESTRATOR_PATH/Structures/desubscribe_container.sh node0
bash $ORCHESTRATOR_PATH/Structures/desubscribe_container.sh node1
bash $ORCHESTRATOR_PATH/Structures/desubscribe_container.sh node2
bash $ORCHESTRATOR_PATH/Structures/desubscribe_container.sh node3

# Host 1 containers
bash $ORCHESTRATOR_PATH/Structures/desubscribe_container.sh node4
bash $ORCHESTRATOR_PATH/Structures/desubscribe_container.sh node5
bash $ORCHESTRATOR_PATH/Structures/desubscribe_container.sh node6
bash $ORCHESTRATOR_PATH/Structures/desubscribe_container.sh node7