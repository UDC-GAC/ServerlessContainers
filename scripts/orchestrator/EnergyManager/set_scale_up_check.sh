#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 argument is needed"
      echo "1 -> check before scaling up: 'boundary' (CPU usage vs quota - boundary) or 'pressure' (CPU pressure >= PRESSURE_THRESHOLD)"
      exit 1
fi

request_data="{\"value\": \"${1}\"}"
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/energy_manager/SCALE_UP_CHECK --data "${request_data}"
