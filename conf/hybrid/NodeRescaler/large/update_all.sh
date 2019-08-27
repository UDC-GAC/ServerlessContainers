#!/usr/bin/env bash


CONF_FOLDER=development/AutomaticRescaler/conf/G5000/NodeRescaler/hybrid/large/

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node0.json http://host35:8000/container/node0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node1.json http://host35:8000/container/node1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node2.json http://host35:8000/container/node2
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node3.json http://host35:8000/container/node3

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node4.json http://host36:8000/container/node4
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node5.json http://host36:8000/container/node5
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node6.json http://host36:8000/container/node6
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node7.json http://host36:8000/container/node7

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node8.json http://host37:8000/container/node8
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node9.json http://host37:8000/container/node9
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node10.json http://host37:8000/container/node10
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node11.json http://host37:8000/container/node11

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node12.json http://host38:8000/container/node12
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node13.json http://host38:8000/container/node13
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node14.json http://host38:8000/container/node14
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node15.json http://host38:8000/container/node15
echo