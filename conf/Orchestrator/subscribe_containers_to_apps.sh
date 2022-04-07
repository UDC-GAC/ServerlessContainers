#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator


bash $ORCHESTRATOR_PATH/Structures/subscribe_container_to_app.sh node0 app1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container_to_app.sh node1 app1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container_to_app.sh node2 app1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container_to_app.sh node3 app1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container_to_app.sh node4 app1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container_to_app.sh node5 app1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container_to_app.sh node6 app1
bash $ORCHESTRATOR_PATH/Structures/subscribe_container_to_app.sh node7 app1
