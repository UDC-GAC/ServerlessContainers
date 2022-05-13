#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

echo "Configuring Guardian"
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh

echo "Configuring Scaler"
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh
bash $ORCHESTRATOR_PATH/Scaler/set_polling_frequency.sh 5
bash $ORCHESTRATOR_PATH/Scaler/set_request_timeout.sh 20

echo "Configuring Structures Snapshoter"
bash $ORCHESTRATOR_PATH/StructuresSnapshoter/activate.sh
bash $ORCHESTRATOR_PATH/StructuresSnapshoter/set_polling_frequency.sh 5

echo "Configuring Database Snapshoter"
bash $ORCHESTRATOR_PATH/DatabaseSnapshoter/activate.sh
bash $ORCHESTRATOR_PATH/DatabaseSnapshoter/set_polling_frequency.sh 5

echo "Configuring Refeeder"
bash $ORCHESTRATOR_PATH/Refeeder/activate.sh
bash $ORCHESTRATOR_PATH/Refeeder/set_window_timelapse.sh 7
bash $ORCHESTRATOR_PATH/Refeeder/set_window_delay.sh 15

echo "Configuring Rebalancer"
bash $ORCHESTRATOR_PATH/Rebalancer/deactivate.sh
bash $ORCHESTRATOR_PATH/Rebalancer/set_window_delay.sh 10
bash $ORCHESTRATOR_PATH/Rebalancer/set_window_timelapse.sh 10
bash $ORCHESTRATOR_PATH/Rebalancer/set_energy_diff_percentage.sh 0.40
bash $ORCHESTRATOR_PATH/Rebalancer/set_energy_stolen_percentage.sh 0.40
bash $ORCHESTRATOR_PATH/Rebalancer/deactivate_user_balancing.sh

