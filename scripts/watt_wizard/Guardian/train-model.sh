#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
source "${scriptDir}/../../conf/WattWizard/load-conf.sh"

if [ -z "${5}" ]
then
      echo "5 arguments are needed"
      echo "1 -> structure (e.g., host, container)"
      echo "2 -> model name (e.g., polyreg_Group_P, sgdregressor_Spread_P_and_L,...)"
      echo "3 -> value for user load (e.g., 100)"
      echo "4 -> value for system load (e.g., 100)"
      echo "5 -> value for power (e.g., 70)"
      exit 1
fi

STRUCTURE="${1}"
MODEL_NAME="${2}"
USER_LOAD=${3}
SYSTEM_LOAD=${4}
POWER=${5}
JSON_DATA="{\"user_load\": [${USER_LOAD}], \"system_load\": [${SYSTEM_LOAD}], \"power\": [${POWER}]}"

curl -X POST -H "Content-Type: application/json" -d "${JSON_DATA}" "http://${WATT_WIZARD_REST_URL}/train/${STRUCTURE}/${MODEL_NAME}"