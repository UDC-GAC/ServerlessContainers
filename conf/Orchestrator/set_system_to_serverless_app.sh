#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

apps=($(jq -r '.apps[].name' ${scriptDir}/layout.json))
resources=( cpu mem )

echo "Deactivate the Guardian, Scaler and Rebalancer service"
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh
bash $ORCHESTRATOR_PATH/Rebalancer/deactivate.sh

echo "Readjust Guardian configuration to the applications scenario"
bash $ORCHESTRATOR_PATH/Guardian/set_to_application.sh
bash $ORCHESTRATOR_PATH/Guardian/set_window_delay.sh 15
bash $ORCHESTRATOR_PATH/Guardian/set_window_timelapse.sh 10
bash $ORCHESTRATOR_PATH/Guardian/set_event_timeout.sh 80
bash $ORCHESTRATOR_PATH/Guardian/set_guardable_resources.sh "${resources[@]}"

echo "Setting applications resources to guarded"
for i in "${apps[@]}"
do
  echo "Application name: $i"
  bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_guarded.sh $i "${resources[@]}"
done

echo "Setting applications to guarded"
for i in "${apps[@]}"
do
  echo "Application name: $i"
	bash $ORCHESTRATOR_PATH/Structures/set_to_guarded.sh $i
done

echo "Activate Guardian, Scaler and Rebalancer services"
bash $ORCHESTRATOR_PATH/Guardian/activate.sh
bash $ORCHESTRATOR_PATH/Scaler/activate.sh
bash $ORCHESTRATOR_PATH/Rebalancer/activate.sh

echo "Setting rule config"
echo "Activate rules"
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh default CpuRescaleUp
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh default CpuRescaleDown
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh default MemRescaleUp
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh default MemRescaleDown
echo "Set the correct amounts"
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh default CpuRescaleUp 200
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh default CpuRescaleUp proportional
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh default MemRescaleUp 2048
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh default MemRescaleUp proportional
