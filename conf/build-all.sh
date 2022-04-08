scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../set_pythonpath.sh

echo "Creating (or removing + creating) the tables"
python3 ${scriptDir}/StateDatabase/other_tables.py
python3 ${scriptDir}/StateDatabase/rules.py
python3 ${scriptDir}/StateDatabase/services.py

echo "Configuring the services"
bash ${scriptDir}/Orchestrator/set_services_config.sh

echo "Configuring the rules"
bash ${scriptDir}/Orchestrator/set_rules_config.sh

echo "Subscribing the hosts"
bash ${scriptDir}/Orchestrator/subscribe_hosts.sh

echo "Subscribing the containers"
bash ${scriptDir}/Orchestrator/subscribe_containers.sh

echo "Subscribing the apps"
bash ${scriptDir}/Orchestrator/subscribe_apps.sh

echo "Subscribing the containers to the apps"
bash ${scriptDir}/Orchestrator/subscribe_containers_to_apps.sh

echo "Configuring the structures"
bash ${scriptDir}/Orchestrator/set_structures_config.sh

echo "Setting everything to untreated"
bash ${scriptDir}/Orchestrator/set_system_to_untreated.sh



