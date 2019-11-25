#!/usr/bin/env bash

CONF_FOLDER=development/ServerlessContainers/conf/scal_32_MB/NodeRescaler/hybrid/large

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node0.json http://host16:8000/container/node0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node1.json http://host16:8000/container/node1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node2.json http://host16:8000/container/node2
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node3.json http://host16:8000/container/node3

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node4.json http://host17:8000/container/node4
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node5.json http://host17:8000/container/node5
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node6.json http://host17:8000/container/node6
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node7.json http://host17:8000/container/node7

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node8.json http://host18:8000/container/node8
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node9.json http://host18:8000/container/node9
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node10.json http://host18:8000/container/node10
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node11.json http://host18:8000/container/node11

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node12.json http://host19:8000/container/node12
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node13.json http://host19:8000/container/node13
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node14.json http://host19:8000/container/node14
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node15.json http://host19:8000/container/node15

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node16.json http://host20:8000/container/node16
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node17.json http://host20:8000/container/node17
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node18.json http://host20:8000/container/node18
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node19.json http://host20:8000/container/node19

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node20.json http://host21:8000/container/node20
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node21.json http://host21:8000/container/node21
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node22.json http://host21:8000/container/node22
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node23.json http://host21:8000/container/node23

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node24.json http://host22:8000/container/node24
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node25.json http://host22:8000/container/node25
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node26.json http://host22:8000/container/node26
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node27.json http://host22:8000/container/node27

curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node28.json http://host23:8000/container/node28
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node29.json http://host23:8000/container/node29
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node30.json http://host23:8000/container/node30
curl -X PUT -H "Content-Type: application/json" -d @$HOME/$CONF_FOLDER/node31.json http://host23:8000/container/node31
echo
