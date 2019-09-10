#!/usr/bin/env bash
export ORCHESTRATOR_PATH=$HOME/development/ServerlessContainers/scripts/Orchestrator

nodes=( node0 node1 node2 node3 node4 node5 node6 node7 node8 node9 node10 node11 node12 node13 node14 node15 \
node16 node17 node18 node19 node20 node21 node22 node23 node24 node25 node26 node27 node28 node29 node30 node31 )
resources=( cpu )

echo "Setting Guardian to guard containers"
bash $ORCHESTRATOR_PATH/Guardian/set_to_container.sh > /dev/null

#echo "Setting container resources to guarded"
#for i in "${nodes[@]}"
#do
#    bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_guarded.sh $i ${resources[@]} > /dev/null
#done

echo "Setting container nodes to guarded"
for i in "${nodes[@]}"
do
	bash $ORCHESTRATOR_PATH/Structures/set_to_guarded.sh $i > /dev/null
done