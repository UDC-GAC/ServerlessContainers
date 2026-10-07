#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 argument is needed"
      echo "1 -> minimum CPU pressure to scale up with SCALE_UP_CHECK = pressure, as a fraction (e.g., 0.05 = 5 % of the CPU demand waiting)"
      exit 1
fi

curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/energy_manager/PRESSURE_THRESHOLD -d '{"value":"'$1'"}'
