#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../../set_pythonpath.sh"

REMOTE_HOST="testing-environment"
echo "Will use remote host named ${REMOTE_HOST}"
echo "Testing if host is reachable"
ping -c 2 ${REMOTE_HOST}

echo "Setting up local redirection of ports to remote host"
tmux new -d -s "COUCHDB_forwarding" "ssh -L 5984:${REMOTE_HOST}:5984 root@${REMOTE_HOST}"
tmux new -d -s "OPENSTDB_forwarding" "ssh -L 4242:${REMOTE_HOST}:4242 root@${REMOTE_HOST}"

echo "Running tests"
nosetests3 \
    ${SERVERLESS_PATH}/src/Guardian/* \
    ${SERVERLESS_PATH}/src/MyUtils/* \
    ${SERVERLESS_PATH}/src/StateDatabase/* \
    ${SERVERLESS_PATH}/src/Snapshoters/* \
    --with-coverage --cover-html --cover-erase --cover-package=src

echo "Removing local redirections"
tmux kill-session -t "COUCHDB_forwarding"
tmux kill-session -t "OPENSTDB_forwarding"

echo "Tests finished running, open the 'cover' directory"