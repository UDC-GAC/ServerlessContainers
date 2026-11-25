#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../../../set_pythonpath.sh"
export LXD_KEY_PATH=${SERVERLESS_PATH}
export LXD_KEY_NAME="lxd-$(hostname)"
export TCP_TRACKER_LOG_PATH="/dev/shm/tcp-tracker-$(hostname)"

# Port priority: NODE_SCALER_PORT environment variable > services_config.yml > 8000
if [ -z "${NODE_SCALER_PORT}" ]; then
    NODE_SCALER_PORT=$(grep -E '^[[:space:]]*NODE_SCALER_PORT[[:space:]]*:' "${SERVERLESS_PATH}/services_config.yml" 2>/dev/null \
        | head -n 1 | cut -d ':' -f 2 | cut -d '#' -f 1 | tr -d "[:space:]\"'")
fi
NODE_SCALER_PORT=${NODE_SCALER_PORT:-8000}

cd ${SERVERLESS_PATH}/src/NodeRescaler && gunicorn3 --bind 0.0.0.0:${NODE_SCALER_PORT} wsgi:node_rescaler -w 2 --threads 2
