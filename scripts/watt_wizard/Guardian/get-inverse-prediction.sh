#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
source "${scriptDir}/../../conf/WattWizard/load-conf.sh"

if [ -z "$4" ]
then
      echo "4 arguments are needed"
      echo "1 -> prediction method (e.g., polyreg, sgdregressor,...)"
      echo "2 -> value for user load (e.g., 300)"
      echo "3 -> value for system load (e.g., 50)"
      echo "4 -> value for desired power (e.g., 120)"
      exit 1
fi

MODEL_NAME="${1}_${TRAIN_FILE_NAME}"
USER_LOAD=${2}
SYSTEM_LOAD=${3}
DESIRED_POWER=${4}

curl -G "${WATT_WIZARD_REST_URL}/inverse-predict/${MODEL_NAME}" --data-urlencode "user_load=${USER_LOAD}" \
                                                   --data-urlencode "system_load=${SYSTEM_LOAD}" \
                                                   --data-urlencode "desired_power=${DESIRED_POWER}"
