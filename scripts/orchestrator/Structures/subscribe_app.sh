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
  "app":
  {
    "name": "'$1'",
    "resources": {
      "cpu": {"max": 1600,  "min": 20,   "guard": false},
      "mem": {"max": 16384, "min": 512,  "guard": false}
    },
    "guard": false,
    "subtype": "application"
  },
  "limits":
  {
    "resources": {
      "cpu": {"boundary": 50},
      "mem": {"boundary": 1024}
    }
  }
}'