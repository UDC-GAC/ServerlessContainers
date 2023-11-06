#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

curl -X PUT -H "Content-Type: application/json" -s http://${ORCHESTRATOR_REST_URL}/service/guardian/ACTIVE -d '{"value":"true"}'