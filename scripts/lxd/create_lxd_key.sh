#!/usr/bin/env bash
KEY_NAME=lxd-`hostname`

openssl genrsa -out ${KEY_NAME}.key 4096
openssl req -new -key ${KEY_NAME}.key -out ${KEY_NAME}.csr
openssl x509 -req -days 3650 -in ${KEY_NAME}.csr -signkey ${KEY_NAME}.key -out ${KEY_NAME}.crt
