#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

#nodes=( node0 node1 node2 node3 node4 node5 node6 node7 )
resources=( cpu )

echo "Setting Guardian to guard applications"
bash $ORCHESTRATOR_PATH/Guardian/set_to_application.sh

echo "Readjust Guardian configuration to the applications scenario"
bash $ORCHESTRATOR_PATH/Guardian/set_window_delay.sh 15
bash $ORCHESTRATOR_PATH/Guardian/set_window_timelapse.sh 10
bash $ORCHESTRATOR_PATH/Guardian/set_event_timeout.sh 80

echo "Setting application to guarded"
bash $ORCHESTRATOR_PATH/Structures/set_to_guarded.sh app1

echo "Setting resources to guarded"
bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_guarded.sh app1 "${resources[@]}"

echo "Activate Guardian and Scaler services"
bash $ORCHESTRATOR_PATH/Guardian/activate.sh
bash $ORCHESTRATOR_PATH/Scaler/activate.sh