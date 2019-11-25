#!/usr/bin/env bash

CONF_FOLDER=development/ServerlessContainers/conf/scal_4_dev/NodeRescaler/

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node0.json http://host0:8000/container/node0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node1.json http://host0:8000/container/node1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node2.json http://host0:8000/container/node2
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node3.json http://host0:8000/container/node3
echo
