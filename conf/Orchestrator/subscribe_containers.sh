#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

# Host 0 containers
bash $ORCHESTRATOR_PATH/Structures/subscribe_container.sh node0 host0
bash $ORCHESTRATOR_PATH/Structures/subscribe_container.sh node1 host0
bash $ORCHESTRATOR_PATH/Structures/subscribe_container.sh node2 host0
bash $ORCHESTRATOR_PATH/Structures/subscribe_container.sh node3 host0


# Host 1 containers
bash $ORCHESTRATOR_PATH/Structures/subscribe_container.sh node4 host1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container.sh node5 host1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container.sh node6 host1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container.sh node7 host1