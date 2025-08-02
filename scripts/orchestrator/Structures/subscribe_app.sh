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
      "cpu": {"max": 1600,  "min": 20,   "guard": false, "weight": 1},
      "mem": {"max": 24576, "min": 512,  "guard": false, "weight": 1}
    },
    "guard": false,
    "subtype": "application",
    "install_script": "",
    "install_files": "",
    "runtime_files": "",
    "output_dir": "",
    "start_script": "",
    "stop_script": "",
    "app_jar": "",
    "framework": ""
  },
  "limits":
  {
    "resources": {
      "cpu": {"boundary": 5, "boundary_type": "percentage_of_max"},
      "mem": {"boundary": 5, "boundary_type": "percentage_of_max"}
    }
  }
}'
