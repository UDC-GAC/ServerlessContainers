#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../../set_pythonpath.sh
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator

jq -c '.users[]' ${scriptDir}/layout.json | while read u; do
    echo "Subscribing user: $(echo ${u} | jq -c '.name')"
    bash $ORCHESTRATOR_PATH/Users/subscribe_user.sh ${u}
done