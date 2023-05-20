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
