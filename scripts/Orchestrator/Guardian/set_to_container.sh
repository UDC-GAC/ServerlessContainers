#!/usr/bin/env bash
GUARDIAN_FILE_CONF_PATH=development/AutomaticRescaler/scripts/Orchestrator/Guardian
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/service/guardian -d @GUARDIAN_FILE_CONF_PATH/container.json