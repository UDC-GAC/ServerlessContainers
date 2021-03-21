#!/usr/bin/env bash
export RESCALER_PATH=$HOME/development/ServerlessContainers
export CONF_FOLDER=$RESCALER_PATH/quickstart/NodeRescaler


curl -X PUT -H "Content-Type: application/json" -d '{"cpu": {"cpu_allowance_limit": "200","cpu_num": "0,1"}}' http://host0:8000/container/cont0
curl -X PUT -H "Content-Type: application/json" -d '{"mem": {"mem_limit": "4096"}}' http://host0:8000/container/cont0
#curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/cont0.json http://host0:8000/container/cont0
curl -X PUT -H "Content-Type: application/json" -d '{"cpu": {"cpu_allowance_limit": "200","cpu_num": "2,3"}}' http://host0:8000/container/cont1
curl -X PUT -H "Content-Type: application/json" -d '{"mem": {"mem_limit": "4096"}}' http://host0:8000/container/cont1
#curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/cont1.json http://host0:8000/container/cont1
echo
