#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 argument is needed"
      echo "1 -> ratio of credits (value given) to 1 GRC (e.g., 600 credits per 1 GRC -> 1 vcore for 10 minutes)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/credit_manager/COINS_TO_CREDIT_RATIO -d '{"value":"'$1'"}'
