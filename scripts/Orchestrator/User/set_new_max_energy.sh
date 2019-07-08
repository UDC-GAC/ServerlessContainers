#!/usr/bin/env bash
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/user/$1/energy/max  -d '{"value":"'$2'"}'
