#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$2" ]
then
      echo "2 Arguments are needed"
      echo "1 -> user in JSON format"
      echo "2 -> value of billing, either 'used' or 'current'"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" -s http://${ORCHESTRATOR_REST_URL}/user/${1}/accounting/billing_type  -d '{"value":"'$2'"}'
