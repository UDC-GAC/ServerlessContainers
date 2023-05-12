#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

hosts=$(jq -c '.hosts[]' ${scriptDir}/layout.json)
while read -r host; do
    name=$(echo $host | jq -r '.name')
    containers=$(echo $host | jq -c '.containers[]' | tr -d '"')
    while read -r container; do
        echo "Subscribing container $container of host $name"
        bash $ORCHESTRATOR_PATH/Structures/subscribe_container.sh $container $name
    done <<< "$containers"
done <<< "$hosts"
