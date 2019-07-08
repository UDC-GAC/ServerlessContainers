#!/usr/bin/env bash

CONF_FOLDER=development/AutomaticRescaler/conf/G5000/NodeRescaler/metagenomics

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/master0.json http://host4:8000/container/master0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/master1.json http://host4:8000/container/master1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/aux0.json http://host4:8000/container/aux0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/pre0.json http://host4:8000/container/pre0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/pre1.json http://host4:8000/container/pre1

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/comp0.json http://host5:8000/container/comp0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/comp1.json http://host5:8000/container/comp1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/comp2.json http://host5:8000/container/comp2
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/pre2.json http://host5:8000/container/pre2

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/pre3.json http://host6:8000/container/pre3
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/comp3.json http://host6:8000/container/comp3
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/comp4.json http://host6:8000/container/comp4
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/comp5.json http://host6:8000/container/comp5
echo