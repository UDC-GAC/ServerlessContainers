#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
source "${scriptDir}/../../conf/WattWizard/load-conf.sh"

if [ -z "$3" ]
then
      echo "3 arguments are needed"
      echo "1 -> variable to be limited (e.g., user_load, system_load)"
      echo "2 -> minimum limit (e.g., 0)"
      echo "3 -> maximum limit (e.g., 6400)"
      exit 1
fi

VAR_NAME=${1}
VAR_MIN=${2}
VAR_MAX=${3}
JSON_DATA="{\"${VAR_NAME}\": {\"min\": ${VAR_MIN}, \"max\":  ${VAR_MAX}}}"

curl -X PUT -H "Content-Type: application/json" -d "${JSON_DATA}" "http://${WATT_WIZARD_REST_URL}/cpu-limits"