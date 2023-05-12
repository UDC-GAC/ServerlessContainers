#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

hosts=($(jq -r '.hosts[].name' ${scriptDir}/layout.json))
for name in "${hosts[@]}"
do
    echo "Desubscribing host: $name"
    bash $ORCHESTRATOR_PATH/Structures/desubscribe_host.sh ${name}
done