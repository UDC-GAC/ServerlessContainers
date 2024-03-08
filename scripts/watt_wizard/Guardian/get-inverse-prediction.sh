#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

WATT_WIZARD_REST_URL="localhost:7777"
PRED_METHOD="polyreg"
TRAIN_FILE_NAME="train"
MODEL_NAME="${PRED_METHOD}_${TRAIN_FILE_NAME}"

USER_SHARES=100
SYSTEM_SHARES=0
DESIRED_POWER=100

curl -G "${WATT_WIZARD_REST_URL}/inverse-predict/${MODEL_NAME}" --data-urlencode "user_load=${USER_SHARES}" \
                                                   --data-urlencode "system_load=${SYSTEM_SHARES}" \
                                                   --data-urlencode "desired_power=${DESIRED_POWER}" \
