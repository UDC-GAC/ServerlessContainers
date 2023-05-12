#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

apps=($(jq -r '.apps[].name' ${scriptDir}/layout.json))
for name in "${apps[@]}"
do
    echo "Desubscribing app: $name"
    bash $ORCHESTRATOR_PATH/Structures/desubscribe_app.sh ${name}
done
