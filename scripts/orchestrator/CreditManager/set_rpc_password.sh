#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 argument is needed"
      echo "1 -> password for the gridcoin RCP server (e.g., BZ2oEfVyuMGqvB26XCALERmDu5bvULKr8NPvPBkMkMSV)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/credit_manager/GRIDCOIN_RPC_PASS -d '{"value":"'$1'"}'
