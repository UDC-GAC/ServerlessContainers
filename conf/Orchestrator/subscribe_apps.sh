#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

app_names=($(jq -r '.apps[].name' ${scriptDir}/layout.json))
for name in "${app_names[@]}"
do
    echo "Subscribing app: $name"
    bash $ORCHESTRATOR_PATH/Structures/subscribe_app.sh ${name}
done
