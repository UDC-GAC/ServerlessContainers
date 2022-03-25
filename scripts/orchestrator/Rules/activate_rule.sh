#!/usr/bin/env bash600
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/rule/$1/activate
