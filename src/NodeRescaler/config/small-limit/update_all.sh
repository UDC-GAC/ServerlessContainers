#!/usr/bin/env bash
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/AutomaticRescaler/src/NodeRescaler/config/small-limit/node0.json http://dante:8000/container/node0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/AutomaticRescaler/src/NodeRescaler/config/small-limit/node1.json http://dante:8000/container/node1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/AutomaticRescaler/src/NodeRescaler/config/small-limit/node2.json http://dante:8000/container/node2
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/AutomaticRescaler/src/NodeRescaler/config/small-limit/node3.json http://dante:8000/container/node3
echo