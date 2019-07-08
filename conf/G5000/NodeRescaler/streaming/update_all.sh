#!/usr/bin/env bash

CONF_FOLDER=development/AutomaticRescaler/conf/G5000/NodeRescaler/streaming

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka0.json http://host7:8000/container/kafka0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/hibench0.json http://host7:8000/container/hibench0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/hibench1.json http://host7:8000/container/hibench1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave9.json http://host7:8000/container/slave9

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka1.json http://host8:8000/container/kafka1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave0.json http://host8:8000/container/slave0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave1.json http://host8:8000/container/slave1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave2.json http://host8:8000/container/slave2

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka2.json http://host9:8000/container/kafka2
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave3.json http://host9:8000/container/slave3
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave4.json http://host9:8000/container/slave4
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave5.json http://host9:8000/container/slave5

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka3.json http://host10:8000/container/kafka3
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave6.json http://host10:8000/container/slave6
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave7.json http://host10:8000/container/slave7
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave8.json http://host10:8000/container/slave8

echo