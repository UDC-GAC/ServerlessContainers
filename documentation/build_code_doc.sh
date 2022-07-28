#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_pythonpath.sh"
mkdir -p web
pdoc3 --html --template-dir code_templates/ --force $SERVERLESS_PATH/src -o web/code