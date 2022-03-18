#!/usr/bin/env bash
export LXD_KEY_NAME="lxd-$(hostname)"

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../../set_pythonpath.sh"
openssl genrsa -out ${SERVERLESS_PATH}/${LXD_KEY_NAME}.key 4096
openssl req -new -key ${SERVERLESS_PATH}/${LXD_KEY_NAME}.key -out ${SERVERLESS_PATH}/${LXD_KEY_NAME}.csr -subj "/C=ES/ST=A Coruna/L=A Coruna/O=UDC-FIC/CN="
openssl x509 -req -days 3650 -in ${SERVERLESS_PATH}/${LXD_KEY_NAME}.csr -signkey ${SERVERLESS_PATH}/${LXD_KEY_NAME}.key -out ${SERVERLESS_PATH}/${LXD_KEY_NAME}.crt