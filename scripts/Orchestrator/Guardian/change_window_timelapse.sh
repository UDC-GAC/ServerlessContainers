#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "Argument not given for new value for WINDOW_TIMELAPSE, using 10 as default"
      value=1
else
    value=$1
fi
echo "Posting new value for WINDOW_TIMELAPSE to ${ORCHESTRATOR_REST_URL}"
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/guardian/WINDOW_TIMELAPSE -d '{"value":"'$value'"}'