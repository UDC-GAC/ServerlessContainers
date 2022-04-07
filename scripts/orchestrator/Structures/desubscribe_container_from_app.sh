#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$2" ]
then
      echo "2 arguments are needed"
      echo "1 -> container name (e.g., node3)"
      echo "2 -> app name (e.g., app1)"
      exit 1
fi

curl -X DELETE -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/structure/container/$1/$2