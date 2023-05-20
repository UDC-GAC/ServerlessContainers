#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

apps=($(jq -r '.apps[].name' ${scriptDir}/layout.json))
containers=$(jq -c '.containers[].name' ${scriptDir}/layout.json | tr -d '"')
resources=( cpu mem )

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

echo "Deactivate Guardian, Scaler and ReBalancer services"
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh
bash $ORCHESTRATOR_PATH/Rebalancer/deactivate.sh

echo "Deactivate rules"
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh default CpuRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh default CpuRescaleDown
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh default MemRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh default MemRescaleDown