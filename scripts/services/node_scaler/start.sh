#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../../../set_pythonpath.sh"
export LXD_KEY_PATH="/root/development/"
export LXD_KEY_NAME="lxd-serv-dev-0"
cd ${SERVERLESS_PATH}/src/NodeRescaler && gunicorn3 --bind 0.0.0.0:8000 wsgi:node_rescaler -w 2 --threads 2
