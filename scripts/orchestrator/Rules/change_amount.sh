#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$3" ]
then
  echo "3 arguments are needed"
  echo "1 -> rule profile (e.g., default, benevolent, strict)"
  echo "2 -> rule name (e.g., CpuRescaleDown)"
  echo "3 -> new amount (e.g., 200)"
  exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/rule/$1/$2/amount  -d '{"value":"'$3'"}'

