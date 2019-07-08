#!/usr/bin/env bash
export ORCHESTRATOR_PATH=$HOME/development/AutomaticRescaler/scripts/Orchestrator

nodes=( aux0 pre0 pre1 pre2 comp0 comp1 comp2 master0 master1 )
apps=( aux_user0 pre_user0 comp_user0 )
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
