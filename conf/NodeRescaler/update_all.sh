#!/usr/bin/env bash

CONF_FOLDER=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/node0.json http://host0:8000/container/node0
curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/node1.json http://host0:8000/container/node1
curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/node2.json http://host0:8000/container/node2
curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/node3.json http://host0:8000/container/node3

curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/node4.json http://host1:8000/container/node4
curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/node5.json http://host1:8000/container/node5
curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/node6.json http://host1:8000/container/node6
curl -X PUT -H "Content-Type: application/json" -d @$CONF_FOLDER/node7.json http://host1:8000/container/node7

echo
