#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]; then
  echo "1 Argument is needed"
  echo "1 -> host structure in json format (e.g.)"
  echo "{
      \"name\": \"host0\",
      \"host\": \"host0\",
      \"host_rescaler_ip\": \"host0\",
      \"host_rescaler_port\": \"8000\",
      \"resources\": {
        \"cpu\": {
          \"max\": 400,
          \"free\": 400
        },
        \"mem\": {
          \"max\": 8192,
          \"free\": 8192
        }
      }
    }"
  exit 1
fi

name=$(echo ${1} | jq -c '.name' | tr -d '"')
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/structure/host/$name -d $1