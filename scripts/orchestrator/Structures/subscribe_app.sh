#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 Argument is needed"
      echo "1 -> app name (e.g., app1)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/structure/apps/$1 -d \
'{
  "name": "'$1'",
  "resources": {
    "cpu": {"max": 1600,  "min": 200,  "guard": false},
    "mem": {"max": 16384, "min": 1024, "guard": false}
  },
  "guard": false,
  "subtype": "application"
}'