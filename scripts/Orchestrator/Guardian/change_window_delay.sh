#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "Argument not given for new value for WINDOW_DELAY, using 10 as default"
      value=10
else
    value=$1
fi
echo "Posting new value for WINDOW_DELAY to ${ORCHESTRATOR_REST_URL}"
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/guardian/WINDOW_DELAY -d '{"value":"'$value'"}'