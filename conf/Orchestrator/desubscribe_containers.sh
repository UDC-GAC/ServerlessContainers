#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

containers=($(jq -r '.containers[].name' ${scriptDir}/layout.json))
for name in "${containers[@]}"
do
    echo "Desubscribing container: $name"
    bash $ORCHESTRATOR_PATH/Structures/desubscribe_container.sh ${name}
done