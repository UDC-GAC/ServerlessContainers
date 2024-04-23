#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "At least 1 argument is needed"
      echo "1 -> model name (e.g. polyreg_General)"
      exit 1
fi

request_data="{\"value\": \"${1}\"}"
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/guardian/ENERGY_MODEL_NAME --data "${request_data}"
