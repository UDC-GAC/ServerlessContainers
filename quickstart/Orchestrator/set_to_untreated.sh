#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../../set_pythonpath.sh"

export ORCHESTRATOR_PATH=$SERVERLESS_PATH/scripts/Orchestrator

nodes=( cont0 cont1 )
resources=( cpu )

echo "Setting Guardian to guard containers"
bash $ORCHESTRATOR_PATH/Guardian/set_to_container.sh 2> /dev/null

echo "Setting container resources to unguarded"
for i in "${nodes[@]}"
do
    bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_unguarded.sh $i "${resources[@]}" 2> /dev/null
done

echo "Setting container nodes to unguarded"
for i in "${nodes[@]}"
do
	bash $ORCHESTRATOR_PATH/Structures/set_to_unguarded.sh $i 2> /dev/null
done
