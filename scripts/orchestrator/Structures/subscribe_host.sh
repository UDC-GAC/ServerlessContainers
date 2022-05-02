#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 Argument is needed"
      echo "1 -> host name (e.g., host0)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/structure/host/$1 -d \
'{
  "name": "'$1'",
  "host": "'$1'",
  "subtype": "host",
  "host_rescaler_ip":  "'$1'",
  "host_rescaler_port": "8000",
  "resources": {
    "cpu": {"max": 800,  "free": 800},
    "mem": {"max": 24576, "free": 24576}
  }
}'