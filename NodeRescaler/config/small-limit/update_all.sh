#!/usr/bin/env bash
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/automatic-rescaler/NodeRescaler/config/small-limit/node0.json http://c14-13:8000/container/node0
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/automatic-rescaler/NodeRescaler/config/small-limit/node1.json http://c14-13:8000/container/node1
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/automatic-rescaler/NodeRescaler/config/small-limit/node2.json http://c14-13:8000/container/node2
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/automatic-rescaler/NodeRescaler/config/small-limit/node3.json http://c14-13:8000/container/node3
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/automatic-rescaler/NodeRescaler/config/small-limit/node4.json http://c14-13:8000/container/node4
curl -X PUT -H "Content-Type: application/json" -d @$HOME/development/automatic-rescaler/NodeRescaler/config/small-limit/node5.json http://c14-13:8000/container/node5
echo