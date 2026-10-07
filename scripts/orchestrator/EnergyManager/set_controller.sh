#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "At least 1 argument is needed"
      echo "1 -> controller: ev, tdp, ppe-proportional, model-boosted, model-only or package.module:Class"
      exit 1
fi

request_data="{\"value\": \"${1}\"}"
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/energy_manager/CONTROLLER --data "${request_data}"
