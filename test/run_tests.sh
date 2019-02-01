#!/usr/bin/env bash

tmux new -d -s "COUCHDB_forwarding" "ssh -L 5984:testing-environment:5984 root@testing-environment"
tmux new -d -s "OPENSTDB_forwarding" "ssh -L 4242:testing-environment:4242 root@testing-environment"
nosetests --with-coverage ..
tmux kill-session -t "COUCHDB_forwarding"
tmux kill-session -t "OPENSTDB_forwarding"
