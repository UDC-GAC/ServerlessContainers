#!/usr/bin/env bash
openssl genrsa -out lxd.key 4096
openssl req -new -key lxd.key -out lxd.csr
openssl x509 -req -days 3650 -in lxd.csr -signkey lxd.key -out lxd.crt
