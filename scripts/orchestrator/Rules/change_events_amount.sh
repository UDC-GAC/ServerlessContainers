#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$4" ]
then
  echo "4 arguments are needed"
  echo "1 -> rule profile (e.g., default, benevolent, strict)"
  echo "2 -> rule name (e.g., CpuRescaleDown)"
  echo "3 -> event type ['up' or 'down']"
  echo "4 -> new events amount (e.g., 2)"
  exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/rule/$1/$2/events_required  -d \
'{"event_type": "'$3'", "value":"'$4'"}'

