scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source ${scriptDir}/../set_pythonpath.sh

echo "Removing apps"
bash ${scriptDir}/Orchestrator/desubscribe_apps.sh

echo "Removing containers"
bash ${scriptDir}/Orchestrator/desubscribe_containers.sh

echo "Removing hosts"
bash ${scriptDir}/Orchestrator/desubscribe_hosts.sh

echo "Removing users"
bash ${scriptDir}/Orchestrator/desubscribe_users.sh
