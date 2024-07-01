#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
source "${scriptDir}/../../conf/WattWizard/load-conf.sh"

if [ -z "${2}" ]
then
      echo "2 arguments are needed"
      echo "1 -> structure (e.g., host, container)"
      echo "2 -> model name (e.g., polyreg_Group_P, sgdregressor_Spread_P_and_L,...)"
      exit 1
fi

STRUCTURE="${1}"
MODEL_NAME="${2}"

curl -X DELETE "http://${WATT_WIZARD_REST_URL}/reset-model/${STRUCTURE}/${MODEL_NAME}"