#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

apps=$(jq -c '.apps[]' ${scriptDir}/layout.json)
while read -r app; do
    name=$(echo $app | jq -r '.name')
    containers=$(echo $app | jq -c '.containers[]' | tr -d '"')
    while read -r container; do
        echo "Subscribing container $container to app $name"
        bash $ORCHESTRATOR_PATH/Structures/subscribe_container_to_app.sh $container $name
    done <<< "$containers"
done <<< "$apps"
