#!/usr/bin/env bash
export ORCHESTRATOR_PATH=$HOME/development/AutomaticRescaler/scripts/Orchestrator

nodes=( master0 master1 kafka0 kafka1 kafka2 kafka3 slave0 slave1 slave2 slave3 slave4 slave5 slave6 slave7 slave8 slave9 hibench0 hiebcnh1 )
apps=( kafkas_user0 kafkas_user1 spark_user0 spark_user1 hibenches_user0 hibenches_user1 )
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
