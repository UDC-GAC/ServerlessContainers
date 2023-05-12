#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

apps=($(jq -r '.apps[].name' ${scriptDir}/layout.json))
containers=$(jq -c '.hosts[].containers[]' ${scriptDir}/layout.json | tr -d '"')

while read -r container; do
    echo "Container name: $container"
    echo "cpu"
    bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_max.sh $container cpu 200
    bash $ORCHESTRATOR_PATH/Limits/set_new_boundary.sh $container cpu 20
    bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_min.sh $container cpu 20

    echo "mem"
    bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_max.sh $container mem 2048
    bash $ORCHESTRATOR_PATH/Limits/set_new_boundary.sh $container mem 350
    bash $ORCHESTRATOR_PATH/Structures/set_structure_resource_min.sh $container mem 512
done <<< "$containers"

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


