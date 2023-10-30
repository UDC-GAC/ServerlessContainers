#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "2 Arguments are needed"
      echo "1 -> user in JSON format"
      echo "2 -> value"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/user/${1}/accounting/max_debt  -d '{"value":"'$2'"}'
