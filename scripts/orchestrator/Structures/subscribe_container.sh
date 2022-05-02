#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$2" ]
then
      echo "2 arguments are needed"
      echo "1 -> container name (e.g., node3)"
      echo "2 -> host name (e.g., host0)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/structure/container/$1 -d \
'{
  "container":
  {
    "name": "'$1'",
    "resources": {
      "cpu": {"max": 200,  "current": 200,  "min": 20,   "guard": false},
      "mem": {"max": 6144, "current": 6144, "min": 512,  "guard": false}
    },
    "host_rescaler_ip": "'$2'",
    "host_rescaler_port": "8000",
    "host": "'$2'",
    "guard": false,
    "subtype": "container"
  },
  "limits":
  {
    "resources": {
      "cpu": {"boundary": 20},
      "mem": {"boundary": 256}
    }
  }
}'