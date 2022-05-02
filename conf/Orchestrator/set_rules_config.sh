#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh CpuRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh CpuRescaleDown
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh MemRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh MemRescaleDown

bash $ORCHESTRATOR_PATH/Rules/change_amount.sh CpuRescaleUp 75
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh CpuRescaleUp up 2
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh CpuRescaleUp down 2

bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh CpuRescaleDown up 0
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh CpuRescaleDown down 6

bash $ORCHESTRATOR_PATH/Rules/change_amount.sh MemRescaleUp 256
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh MemRescaleUp up 2
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh MemRescaleUp down 6

bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh MemRescaleDown up 0
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh MemRescaleDown down 8