scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../set_pythonpath.sh
export CONF_PATH=${SERVERLESS_PATH}/conf

python3 ${CONF_PATH}/StateDatabase/events_and_requests.py
python3 ${CONF_PATH}/StateDatabase/rules.py
python3 ${CONF_PATH}/StateDatabase/limits.py
python3 ${CONF_PATH}/StateDatabase/structures.py
python3 ${CONF_PATH}/StateDatabase/services.py
python3 ${CONF_PATH}/StateDatabase/reset_host_structure_info.py
