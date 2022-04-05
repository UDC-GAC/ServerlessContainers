#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "At least 1 argument is needed"
      echo "1 and following -> space separated list of resources (e.g., cpu mem)"
      exit 1
fi

request_data=`python3 -c 'import json, sys; print(json.dumps({"value":[v for v in sys.argv[1:]]}))' "${@:1}"`
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/guardian/GUARDABLE_RESOURCES --data "${request_data}"
