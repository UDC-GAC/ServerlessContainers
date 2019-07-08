#!/usr/bin/env bash
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/structure/$1/resources/energy/shares -d '{"value":"'$2'"}'