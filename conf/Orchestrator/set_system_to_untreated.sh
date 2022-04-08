#!/usr/bin/env bash

export SERVERLESS_PATH=$HOME/ServerlessContainers
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

apps=( app1 )
nodes=( node0 node1 node2 node3 node4 node5 node6 node7 )
resources=( cpu mem )

echo "Setting container resources to unguarded"
for i in "${nodes[@]}"
do
    bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_unguarded.sh $i "${resources[@]}"
done

echo "Setting container nodes to unguarded"
for i in "${nodes[@]}"
do
	bash $ORCHESTRATOR_PATH/Structures/set_to_unguarded.sh $i
done

echo "Setting applications resources to unguarded"
for i in "${apps[@]}"
do
    bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_unguarded.sh $i "${resources[@]}"
done

echo "Setting applications to unguarded"
for i in "${apps[@]}"
do
	bash $ORCHESTRATOR_PATH/Structures/set_to_unguarded.sh $i
done

echo "Deactivate StructureSnapshoter, DatabaseSnapshoter, Guardian and Scaler services"
bash $ORCHESTRATOR_PATH/StructuresSnapshoter/deactivate.sh
bash $ORCHESTRATOR_PATH/DatabaseSnapshoter/deactivate.sh
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh

echo "Deactivate rules"
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh CpuRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh CpuRescaleDown
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh MemRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh MemRescaleDown