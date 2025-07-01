#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"


if [ -z "$3" ]
then
      echo "3 arguments are needed"
      echo "1 -> structure name (e.g., node3, app1)"
      echo "2 -> resource name (e.g., cpu, mem)"
      echo "3 -> boundary type value (e.g., percentage_of_max)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/structure/$1/limits/$2/boundary_type  -d '{"value":"'$3'"}'
