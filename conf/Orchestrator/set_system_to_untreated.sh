#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

apps=($(jq -r '.apps[].name' ${scriptDir}/layout.json))
containers=$(jq -c '.hosts[].containers[]' ${scriptDir}/layout.json | tr -d '"')
resources=( cpu )

echo "Setting container resources to unguarded"
while read -r container; do
    echo "Container name: $container"
    bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_unguarded.sh ${container} "${resources[@]}"
done <<< "$containers"

echo "Setting container nodes to unguarded"
while read -r container; do
    echo "Container name: $container"
    bash $ORCHESTRATOR_PATH/Structures/set_to_unguarded.sh ${container}
done <<< "$containers"

echo "Setting applications resources to unguarded"
for i in "${apps[@]}"
do
    echo "Application: '${i}'"
    bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_unguarded.sh $i "${resources[@]}"
done

echo "Setting applications to unguarded"
for i in "${apps[@]}"
do
  echo "Application: '${i}'"
	bash $ORCHESTRATOR_PATH/Structures/set_to_unguarded.sh $i
done

echo "Deactivate StructureSnapshoter, DatabaseSnapshoter, Guardian and Scaler services"
#bash $ORCHESTRATOR_PATH/StructuresSnapshoter/deactivate.sh
#bash $ORCHESTRATOR_PATH/DatabaseSnapshoter/deactivate.sh
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh

echo "Deactivate rules"
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh CpuRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh CpuRescaleDown
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh MemRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh MemRescaleDown