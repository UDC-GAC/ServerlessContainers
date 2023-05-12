#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

host_names=($(jq -r '.hosts[].name' ${scriptDir}/layout.json))
for name in "${host_names[@]}"
do
    echo "Subscribing host: $name"
    bash $ORCHESTRATOR_PATH/Structures/subscribe_host.sh ${name}
done
