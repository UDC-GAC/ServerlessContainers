#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
request_data=`python -c 'import json, sys; print(json.dumps({"resources":[v for v in sys.argv[1:]]}))' ${@:2}`
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/structure/$1/resources/unguard --data "${request_data}"