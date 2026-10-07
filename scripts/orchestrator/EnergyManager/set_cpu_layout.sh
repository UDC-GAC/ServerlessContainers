#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$1" ]
then
      echo "1 argument is needed"
      echo "1 -> how CPUs are chosen when the CPU of a container is scaled: 'topology' (no CPUs isolated in another socket, see src/EnergyManager/topology.py) or 'scaler' (Scaler order, Group_PP_LL)"
      exit 1
fi

request_data="{\"value\": \"${1}\"}"
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/service/energy_manager/CPU_LAYOUT --data "${request_data}"
