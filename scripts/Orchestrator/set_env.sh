#!/usr/bin/env bash
if [ -z "${ORCHESTRATOR_URL}" ]
then
      ORCHESTRATOR_URL="orchestrator"
fi

if [ -z "${ORCHESTRATOR_PORT}" ]
then
      ORCHESTRATOR_PORT="5000"
fi

if [ -z "${ORCHESTRATOR_BASE_PATH}" ]
then
      URL="${ORCHESTRATOR_URL}:${ORCHESTRATOR_PORT}"
else
      URL="${ORCHESTRATOR_URL}:${ORCHESTRATOR_PORT}/${ORCHESTRATOR_BASE_PATH}"
fi
export ORCHESTRATOR_REST_URL=${URL}



if [ -z "${COUCHDB_URL}" ]
then
      COUCHDB_URL="couchdb"
fi

if [ -z "${COUCHDB_PORT}" ]
then
      COUCHDB_PORT="5984"
fi

if [ -z "${COUCHDB_BASE_PATH}" ]
then
      URL="${COUCHDB_URL}:${COUCHDB_PORT}"
else
      URL="${COUCHDB_URL}:${COUCHDB_PORT}/${COUCHDB_BASE_PATH}"
fi
export COUCHDB_REST_URL=${URL}
