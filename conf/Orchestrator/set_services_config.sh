#!/usr/bin/env bash

export SERVERLESS_PATH=$HOME/ServerlessContainers
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator


bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh

bash $ORCHESTRATOR_PATH/Guardian/set_to_container.sh
bash $ORCHESTRATOR_PATH/Guardian/set_window_delay.sh 6
bash $ORCHESTRATOR_PATH/Guardian/set_window_timelapse.sh 6
bash $ORCHESTRATOR_PATH/Guardian/set_event_timeout.sh 50

bash $ORCHESTRATOR_PATH/Guardian/set_guardable_resources.sh cpu mem

bash $ORCHESTRATOR_PATH/Guardian/activate.sh