#!/usr/bin/env bash

export SERVERLESS_PATH=$HOME/ServerlessContainers
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

apps=( app1 )
nodes=( node0 node1 node2 node3 node4 node5 node6 node7 )

for i in "${nodes[@]}"
do
    echo "Setting node $i"
    echo "cpu"
    bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_max.sh $i cpu 200
    bash $ORCHESTRATOR_PATH/Limits/set_new_boundary.sh $i cpu 20
    bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_min.sh $i cpu 20

    echo "mem"
    bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_max.sh $i mem 2048
    bash $ORCHESTRATOR_PATH/Limits/set_new_boundary.sh $i mem 350
    bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_min.sh $i mem 512
done

for i in "${apps[@]}"
do
  echo "Setting app $i"
  echo "cpu"
  bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_max.sh $i cpu 1600
  bash $ORCHESTRATOR_PATH/Limits/set_new_boundary.sh $i cpu 200
  bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_min.sh $i cpu 200

  echo "mem"
  bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_max.sh $i mem 16384
  bash $ORCHESTRATOR_PATH/Limits/set_new_boundary.sh $i mem 1500
  bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_min.sh $i mem 1024
done


