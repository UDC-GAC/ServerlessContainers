#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$2" ]
then
      echo "2 arguments are needed"
      echo "1 -> structure name (e.g., node3, app1)"
      echo "2 -> energy shares amount (e.g., 200)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/structure/$1/resources/energy/shares -d '{"value":"'$2'"}'
