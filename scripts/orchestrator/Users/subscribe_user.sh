#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 Argument is needed"
      echo "1 -> user in JSON format"
      exit 1
fi

name=$(echo ${1} | jq -c '.name' | tr -d '"')
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/user/${name} -d $1
