#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
source "${scriptDir}/../../conf/WattWizard/load-conf.sh"

if [ -z "$1" ]
then
      echo "3 arguments are needed"
      echo "1 -> model name (e.g., polyreg_Group_P, sgdregressor_Spread_P_and_L,...)"
      exit 1
fi

MODEL_NAME="${1}"

curl -X DELETE "http://${WATT_WIZARD_REST_URL}/reset-model/${MODEL_NAME}"