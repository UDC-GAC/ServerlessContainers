#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
tmux kill-session -t "orchestrator"

# Port priority: ORCHESTRATOR_PORT environment variable > services_config.yml > 5000
if [ -z "${ORCHESTRATOR_PORT}" ]; then
    ORCHESTRATOR_PORT=$(grep -E '^[[:space:]]*ORCHESTRATOR_PORT[[:space:]]*:' "${scriptDir}/../../../services_config.yml" 2>/dev/null \
        | head -n 1 | cut -d ':' -f 2 | cut -d '#' -f 1 | tr -d "[:space:]\"'")
fi
ORCHESTRATOR_PORT=${ORCHESTRATOR_PORT:-5000}

GUNICORN_DAEMON=$(ps aux | grep "[g]unicorn3 --bind 0.0.0.0:${ORCHESTRATOR_PORT}" | awk '{print $2}')
if [ -n "${GUNICORN_DAEMON}" ]; then
    kill ${GUNICORN_DAEMON}
fi
