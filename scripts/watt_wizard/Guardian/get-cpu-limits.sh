#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

curl -G "http://${WATT_WIZARD_REST_URL}/cpu-limits"