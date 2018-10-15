#!/usr/bin/env bash
request_data=`python -c 'import json, sys; print(json.dumps({"resources":[v for v in sys.argv[1:]]}))' ${@:2}`
curl -s -X PUT -H "Content-Type: application/json" http://orchestrator:5000/structure/$1/resources/unguard --data "${request_data}"