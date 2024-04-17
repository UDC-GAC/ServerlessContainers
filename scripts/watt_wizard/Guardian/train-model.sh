#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
source "${scriptDir}/../../conf/WattWizard/load-conf.sh"

if [ -z "$4" ]
then
      echo "4 arguments are needed"
      echo "1 -> model name (e.g., polyreg_Group_P, sgdregressor_Spread_P_and_L,...)"
      echo "2 -> value for user load (e.g., 100)"
      echo "3 -> value for system load (e.g., 100)"
      echo "3 -> value for power (e.g., 70)"
      exit 1
fi

MODEL_NAME=${1}
USER_LOAD=${2}
SYSTEM_LOAD=${3}
POWER=${4}
JSON_DATA="{\"user_load\": [${USER_LOAD}], \"system_load\": [${SYSTEM_LOAD}], \"power\": [${POWER}]}"

echo $JSON_DATA

curl -X POST -H "Content-Type: application/json" -d "${JSON_DATA}" "http://${WATT_WIZARD_REST_URL}/train/${MODEL_NAME}"