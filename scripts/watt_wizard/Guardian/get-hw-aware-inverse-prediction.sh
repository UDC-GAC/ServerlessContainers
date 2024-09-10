#!/usr/bin/env bash

scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "${7}" ]
then
      echo "7 arguments are needed"
      echo "1 -> structure (e.g., host, container)"
      echo "2 -> model name (e.g., polyreg_Group_P, sgdregressor_Spread_P_and_L,...)"
      echo "3 -> value for user load (e.g., 300)"
      echo "4 -> value for system load (e.g., 50)"
      echo "5 -> value for desired power (e.g., 120)"
      echo "6 -> core usages (e.g., 0:user_load=100,system_load=0;2:user_load=30,system_load=5;8:user_load=100,system_load=0)"
      echo "7 -> host cores mapping (e.g., 0=0,1=100,2=65,3=100,4=100,5=100,6=100,7=100,8=0,9=100,10=100)"

      exit 1
fi

STRUCTURE="${1}"
MODEL_NAME="${2}"
USER_LOAD=${3}
SYSTEM_LOAD=${4}
DESIRED_POWER=${5}

IFS=';' read -ra CORE_USAGES_ARRAY <<< "${6}"
CORE_USAGES="{"
for CORE_USAGE in "${CORE_USAGES_ARRAY[@]}"; do
  IFS=':' read CORE ALL_USAGES <<< "${CORE_USAGE}"
  IFS=',' read -ra VAR_USAGES_ARRAY <<< "${ALL_USAGES}"
  CORE_USAGES+="\"${CORE}\":{"
  for VAR_USAGE in "${VAR_USAGES_ARRAY[@]}"; do
    IFS='=' read VAR USAGE <<< "${VAR_USAGE}"
    CORE_USAGES+="\"${VAR}\":${USAGE},"
  done
  CORE_USAGES="${CORE_USAGES::-1}"
  CORE_USAGES+="},"
done
CORE_USAGES="${CORE_USAGES::-1}"
CORE_USAGES+="}"

IFS=',' read -ra FREE_CORES_ARRAY <<< "${7}"
HOST_CORES_MAPPING="{"
for FREE_CORE in "${FREE_CORES_ARRAY[@]}"; do
  IFS='=' read CORE FREE_AMOUNT <<< "${FREE_CORE}"
  HOST_CORES_MAPPING+="\"${CORE}\":{\"free\":${FREE_AMOUNT}},"
done
HOST_CORES_MAPPING="${HOST_CORES_MAPPING::-1}"
HOST_CORES_MAPPING+="}"

curl -G "http://${WATT_WIZARD_REST_URL}/inverse-predict/${STRUCTURE}/${MODEL_NAME}" \
                                                   --data-urlencode "user_load=${USER_LOAD}" \
                                                   --data-urlencode "system_load=${SYSTEM_LOAD}" \
                                                   --data-urlencode "dynamic_var=user_load" \
                                                   --data-urlencode "desired_power=${DESIRED_POWER}" \
                                                   --data-urlencode "core_usages=${CORE_USAGES}" \
                                                   --data-urlencode "host_cores_mapping=${HOST_CORES_MAPPING}"
