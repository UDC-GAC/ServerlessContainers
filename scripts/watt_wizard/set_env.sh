#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
SERVICES_CONFIG_FILE=$scriptDir"/../../services_config.yml"

watt_wizard_url=`yq -r '.WATT_WIZARD_URL' < $SERVICES_CONFIG_FILE`
watt_wizard_port=`yq -r '.WATT_WIZARD_PORT' < $SERVICES_CONFIG_FILE`

if [ -z "${WATT_WIZARD_URL}" ]
then
      WATT_WIZARD_URL=$watt_wizard_url
fi

if [ -z "${WATT_WIZARD_PORT}" ]
then
      WATT_WIZARD_PORT=$watt_wizard_port
fi

WATT_WIZARD_URL="localhost" # Overwritten because name resolution is not configured
export WATT_WIZARD_REST_URL="${WATT_WIZARD_URL}:${WATT_WIZARD_PORT}"
