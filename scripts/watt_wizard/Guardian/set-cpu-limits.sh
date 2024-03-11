#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
source "${scriptDir}/../../conf/WattWizard/load-conf.sh"

if [ -z "$2" ]
then
      echo "2 arguments are needed"
      echo "1 -> variable to be limited (e.g., user_load, system_load)"
      echo "2 -> maximum limit (e.g., 6400)"
      exit 1
fi

VAR_NAME=${1}
VAR_LIMIT=${2}
JSON_DATA="{\"${VAR_NAME}\": {\"min\": 0, \"max\":  ${VAR_LIMIT}}}"

curl -X PUT -H "Content-Type: application/json" -d "${JSON_DATA}" "http://${WATT_WIZARD_REST_URL}/cpu-limits"