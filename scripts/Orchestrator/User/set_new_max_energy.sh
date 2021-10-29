#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/user/$1/energy/max  -d '{"value":"'$2'"}'
