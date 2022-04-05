#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
request_data=`python3 -c 'import json, sys; print(json.dumps({"resources":[v for v in sys.argv[1:]]}))' "${@:2}"`

if [ -z "$2" ]
then
      echo "Several arguments are needed"
      echo "1 -> structure name (e.g., node3, app1)"
      echo "remaining -> resource names, space separated (e.g., cpu mem)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/structure/$1/resources/unguard --data "${request_data}"
