#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 argument is needed"
      echo "1 -> amount for event timeout (e.g., 30)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/energy_controller/EVENT_TIMEOUT -d '{"value":"'$1'"}'
