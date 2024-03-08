#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../../../set_pythonpath.sh"

# Load WattWizard configuration options
source ${SERVERLESS_PATH}/conf/WattWizard/load-conf.sh
OPTS="--vars ${MODEL_VARIABLES} -p ${PREDICTION_METHODS} --train-timestamps ${TRAIN_FILE} -b ${INFLUXDB_BUCKET}"

python3 ${SERVERLESS_PATH}/src/WattWizard/WattWizard.py ${OPTS}