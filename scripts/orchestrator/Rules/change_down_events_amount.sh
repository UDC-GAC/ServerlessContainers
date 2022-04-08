#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$2" ]
then
      echo "2 arguments are needed"
      echo "1 -> rule name (e.g., CpuRescaleDown)"
      echo "2 -> new events amount (e.g., 2)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/rule/$1/events_up_required  -d '{"value":"'$2'"}'

