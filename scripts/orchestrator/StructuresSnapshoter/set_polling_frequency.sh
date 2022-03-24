#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "Argument is needed"
      exit 1
fi
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/structures_snapshoter/POLLING_FREQUENCY -d '{"value":"'$1'"}'