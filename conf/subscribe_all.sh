scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../set_pythonpath.sh

echo "Subscribing the hosts"
bash ${scriptDir}/Orchestrator/subscribe_hosts.sh

echo "Subscribing the containers"
bash ${scriptDir}/Orchestrator/subscribe_containers.sh

echo "Subscribing the apps"
bash ${scriptDir}/Orchestrator/subscribe_apps.sh

echo "Subscribing the user"
bash ${scriptDir}/Orchestrator/subscribe_users.sh

#echo "Setting everything to untreated"
#bash ${scriptDir}/Orchestrator/set_system_to_untreated.sh

echo "Deactivate Guardian, Scaler and CreditManager services"
export ORCHESTRATOR_PATH=${SERVERLESS_PATH}/scripts/orchestrator
bash $ORCHESTRATOR_PATH/Guardian/deactivate.sh
bash $ORCHESTRATOR_PATH/Scaler/deactivate.sh
bash $ORCHESTRATOR_PATH/CreditManager/deactivate.sh


