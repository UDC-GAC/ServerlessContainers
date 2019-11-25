#!/usr/bin/env bash

CONF_FOLDER=development/ServerlessContainers/conf/scal_32_ST/NodeRescaler/

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka0.json http://host28:8000/container/kafka0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/hibench0.json http://host28:8000/container/hibench0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/hibench1.json http://host28:8000/container/hibench1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave9.json http://host28:8000/container/slave9

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka1.json http://host29:8000/container/kafka1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave0.json http://host29:8000/container/slave0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave1.json http://host29:8000/container/slave1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave2.json http://host29:8000/container/slave2

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka2.json http://host30:8000/container/kafka2
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave3.json http://host30:8000/container/slave3
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave4.json http://host30:8000/container/slave4
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave5.json http://host30:8000/container/slave5

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka3.json http://host31:8000/container/kafka3
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave6.json http://host31:8000/container/slave6
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave7.json http://host31:8000/container/slave7
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave8.json http://host31:8000/container/slave8

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka4.json http://host32:8000/container/kafka4
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/hibench2.json http://host32:8000/container/hibench2
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/hibench3.json http://host32:8000/container/hibench3
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave19.json http://host32:8000/container/slave19

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka5.json http://host33:8000/container/kafka5
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave10.json http://host33:8000/container/slave10
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave11.json http://host33:8000/container/slave11
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave12.json http://host33:8000/container/slave12

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka6.json http://host34:8000/container/kafka6
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave13.json http://host34:8000/container/slave13
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave14.json http://host34:8000/container/slave14
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave15.json http://host34:8000/container/slave15

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/kafka7.json http://host35:8000/container/kafka7
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave16.json http://host35:8000/container/slave16
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave17.json http://host35:8000/container/slave17
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/slave18.json http://host35:8000/container/slave18
echo
