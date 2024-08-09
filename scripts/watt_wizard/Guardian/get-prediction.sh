#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "${4}" ]
then
      echo "4 arguments are needed"
      echo "1 -> structure (e.g., host, container)"
      echo "2 -> model name (e.g., polyreg_Group_P, sgdregressor_Spread_P_and_L,...)"
      echo "3 -> value for user load (e.g., 300)"
      echo "4 -> value for system load (e.g., 50)"
      exit 1
fi

STRUCTURE="${1}"
MODEL_NAME="${2}"
USER_LOAD=${3}
SYSTEM_LOAD=${4}

curl -G "http://${WATT_WIZARD_REST_URL}/predict/${STRUCTURE}/${MODEL_NAME}" --data-urlencode "user_load=${USER_LOAD}" \
                                                   --data-urlencode "system_load=${SYSTEM_LOAD}"