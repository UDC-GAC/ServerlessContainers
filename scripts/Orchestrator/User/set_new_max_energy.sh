#!/usr/bin/env bash
curl -X PUT -H "Content-Type: application/json" http://${ORCHESTRATOR_REST_URL}/user/$1/energy/max  -d '{"value":"'$2'"}'
