scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../set_pythonpath.sh
export CONF_PATH=${SERVERLESS_PATH}/conf

python3 ${CONF_PATH}/StateDatabase/events_and_requests.py
python3 ${CONF_PATH}/StateDatabase/rules.py
python3 ${CONF_PATH}/StateDatabase/limits.py
python3 ${CONF_PATH}/StateDatabase/services.py
