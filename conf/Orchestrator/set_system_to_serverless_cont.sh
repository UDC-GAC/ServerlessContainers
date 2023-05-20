#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

containers=$(jq -c '.hosts[].containers[]' ${scriptDir}/layout.json | tr -d '"')
resources=( cpu mem )

echo "Deactivate the Guardian and Scaler service"
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh

echo "Readjust Guardian configuration to the containers scenario"
bash $ORCHESTRATOR_PATH/Guardian/set_to_container.sh
bash $ORCHESTRATOR_PATH/Guardian/set_window_delay.sh 10
bash $ORCHESTRATOR_PATH/Guardian/set_window_timelapse.sh 10
bash $ORCHESTRATOR_PATH/Guardian/set_event_timeout.sh 80
bash $ORCHESTRATOR_PATH/Guardian/set_guardable_resources.sh "${resources[@]}"

echo "Setting container resources to guarded"
while read -r container; do
    echo "Container name: $container"
    bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_guarded.sh ${container} "${resources[@]}"
done <<< "$containers"

echo "Setting container nodes to guarded"
while read -r container; do
    echo "Container name: $container"
    bash $ORCHESTRATOR_PATH/Structures/set_to_guarded.sh ${container}
done <<< "$containers"

echo "Activate Guardian and Scaler services"
bash $ORCHESTRATOR_PATH/Guardian/activate.sh
bash $ORCHESTRATOR_PATH/Scaler/activate.sh

echo "Setting rule config"
echo "Activate rules"
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh default CpuRescaleUp
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh default CpuRescaleDown
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh default MemRescaleUp
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh default MemRescaleDown
echo "Set the correct amounts"
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh default CpuRescaleUp 75
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh default CpuRescaleUp amount
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh default MemRescaleUp 256
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh default MemRescaleUp amount

echo "Deactivate ReBalancer services"
bash $ORCHESTRATOR_PATH/Rebalancer/deactivate.sh