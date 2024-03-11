#!/usr/bin/env bash

confDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

export TRAIN_FILE_NAME=train
export TRAIN_FILE=${confDir}/${TRAIN_FILE_NAME}.timestamps
export MODEL_VARIABLES="user_load,system_load"
export PREDICTION_METHODS="polyreg,sgdregressor"
export INFLUXDB_BUCKET="compute2"