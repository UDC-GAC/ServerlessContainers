#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

nodes=( node0 node1 node2 node3 node4 node5 node6 node7 )
#resources=( cpu mem )
resources=( cpu )

echo "Setting Guardian to guard containers"
bash $ORCHESTRATOR_PATH/Guardian/set_to_container.sh

echo "Readjust Guardian configuration to the containers scenario"
bash $ORCHESTRATOR_PATH/Guardian/set_window_delay.sh 10
bash $ORCHESTRATOR_PATH/Guardian/set_window_timelapse.sh 10
bash $ORCHESTRATOR_PATH/Guardian/set_event_timeout.sh 80

echo "Setting container resources to guarded"
for i in "${nodes[@]}"
do
    bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_guarded.sh $i "${resources[@]}"
done

echo "Setting container nodes to guarded"
for i in "${nodes[@]}"
do
	bash $ORCHESTRATOR_PATH/Structures/set_to_guarded.sh $i
done

echo "Activate Guardian and Scaler services"
bash $ORCHESTRATOR_PATH/Guardian/activate.sh
bash $ORCHESTRATOR_PATH/Scaler/activate.sh