#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "At least 1 argument is needed"
      echo "1 and following -> space separated list of models to train (e.g., polyreg_General sgdregressor_General)"
      exit 1
fi

request_data=`python3 -c 'import json, sys; print(json.dumps({"value":[v for v in sys.argv[1:]]}))' "${@:1}"`
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/watt_trainer/MODELS_TO_TRAIN --data "${request_data}"
