#!/usr/bin/env bash
export ORCHESTRATOR_PATH=$HOME/development/AutomaticRescaler/scripts/Orchestrator

nodes=( node0 node1 node2 node3 node4 node5 node6 node7 node8 node9 node10 node11 node12 node13 node14 node15 )
apps=( app1 )
resources=( energy )
energy_rules=( EnergyRescaleDown EnergyRescaleUp energy_dropped_lower energy_exceeded_upper )

echo "Setting Guardian to guard applications and its energy"
bash $ORCHESTRATOR_PATH/Guardian/set_to_energy.sh > /dev/null

echo "Setting applications to guarded"
for i in "${apps[@]}"
do
	status=$(bash $ORCHESTRATOR_PATH/Structures/set_to_guarded.sh $i)
	if [ "$status" != "201" ]; then
        echo "Error $status setting app $i"
    fi
done

echo "Setting policy to serverless"
for i in "${apps[@]}"
do
	status=$(bash $ORCHESTRATOR_PATH/Structures/set_policy_to_serverless.sh $i)
	if [ "$status" != "201" ]; then
        echo "Error $status setting policy for app $i"
    fi
done

echo "Setting application resources [energy] to guarded"
for i in "${apps[@]}"
do
	status=$(bash $ORCHESTRATOR_PATH/Structures/set_resource_to_guarded.sh $i energy)
	if [ "$status" != "201" ]; then
        echo "Error $status setting energy to guarded for app $i"
    fi
done

echo "Activating energy rules"
for i in "${energy_rules[@]}"
do
    status=$(bash $ORCHESTRATOR_PATH/Rules/activate_rule.sh $i)
    if [ "$status" != "201" ]; then
        echo "Error $status activating energy rule $i"
    fi
done