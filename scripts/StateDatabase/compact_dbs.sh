#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../Orchestrator/set_env.sh"

ACCESS="admin:admin"

curl -X POST -H "Content-Type: application/json" http://${ACCESS}@${COUCHDB_REST_URL}/events/_compact
curl -X POST -H "Content-Type: application/json" http://${ACCESS}@${COUCHDB_REST_URL}/requests/_compact
curl -X POST -H "Content-Type: application/json" http://${ACCESS}@${COUCHDB_REST_URL}/limits/_compact
curl -X POST -H "Content-Type: application/json" http://${ACCESS}@${COUCHDB_REST_URL}/services/_compact
curl -X POST -H "Content-Type: application/json" http://${ACCESS}@${COUCHDB_REST_URL}/rules/_compact
curl -X POST -H "Content-Type: application/json" http://${ACCESS}@${COUCHDB_REST_URL}/structures/_compact
