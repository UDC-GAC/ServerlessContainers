#!/usr/bin/env bash
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/guardian/STRUCTURE_GUARDED -d '{"value":"application"}'