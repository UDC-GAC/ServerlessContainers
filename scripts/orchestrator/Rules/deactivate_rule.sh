#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$2" ]; then
  echo "2 arguments are needed"
  echo "1 -> rule profile (e.g., default, benevolent, strict)"
  echo "2 -> rule name (e.g., cpu_dropped_lower)"
  exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/rule/$1/$2/deactivate
