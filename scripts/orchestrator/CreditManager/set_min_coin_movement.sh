#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 argument is needed"
      echo "1 -> min amount of GRC per each movement (e.g., 0.1 -> movement between wallets will be a minimum of 0.1 and then in multiples)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/credit_manager/MIN_COIN_MOVEMENT -d '{"value":"'$1'"}'
