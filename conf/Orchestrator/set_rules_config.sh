#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

PROFILE="default"
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh ${PROFILE} CpuRescaleUp
bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh ${PROFILE} CpuRescaleDown
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} MemRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} MemRescaleDown
PROFILE="benevolent"
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} CpuRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} CpuRescaleDown
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} MemRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} MemRescaleDown
PROFILE="strict"
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} CpuRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} CpuRescaleDown
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} MemRescaleUp
bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh ${PROFILE} MemRescaleDown


PROFILE="default"
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh ${PROFILE} CpuRescaleUp 75
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleUp up 2
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleUp down 2
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh ${PROFILE} CpuRescaleUp proportional # amount
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleDown up 0
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleDown down 8
PROFILE="benevolent"
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh ${PROFILE} CpuRescaleUp 75
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleUp up 2
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleUp down 2
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh ${PROFILE} CpuRescaleUp proportional # amount
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleDown up 0
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleDown down 8
PROFILE="strict"
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh ${PROFILE} CpuRescaleUp 25
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleUp up 6
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleUp down 0
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh ${PROFILE} CpuRescaleUp proportional # amount
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleDown up 2
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} CpuRescaleDown down 2


PROFILE="default"
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh ${PROFILE} MemRescaleUp 256
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleUp up 2
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleUp down 2
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh ${PROFILE} MemRescaleUp proportional # amount
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleDown up 0
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleDown down 6
PROFILE="benevolent"
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh ${PROFILE} MemRescaleUp 512
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleUp up 2
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleUp down 2
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh ${PROFILE} MemRescaleUp proportional # amount
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleDown up 0
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleDown down 8
PROFILE="strict"
bash $ORCHESTRATOR_PATH/Rules/change_amount.sh ${PROFILE} MemRescaleUp 256
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleUp up 2
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleUp down 0
bash $ORCHESTRATOR_PATH/Rules/change_policy.sh ${PROFILE} MemRescaleUp proportional # amount
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleDown up 2
bash $ORCHESTRATOR_PATH/Rules/change_events_amount.sh ${PROFILE} MemRescaleDown down 4

