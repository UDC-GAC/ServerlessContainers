#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

jq -c '.hosts[]' ${scriptDir}/layout.json | while read h; do
    echo "Subscribing host: $(echo ${h} | jq -c '.name')"
    bash $ORCHESTRATOR_PATH/Structures/subscribe_host.sh ${h}
done
