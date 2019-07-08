#!/usr/bin/env bash
export ORCHESTRATOR_PATH=$HOME/development/AutomaticRescaler/scripts/Orchestrator

nodes=( master0 master1 kafka0 kafka1 kafka2 kafka3 slave0 slave1 slave2 slave3 slave4 slave5 slave6 slave7 slave8 slave9 hibench0 hiebcnh1 )
apps=( kafkas_user0 kafkas_user1 spark_user0 spark_user1 hibenches_user0 hibenches_user1 )
resources=( energy )
energy_rules=( EnergyRescaleDown EnergyRescaleUp energy_dropped_lower energy_exceeded_upper )

echo "Setting Guardian to guard containers"
bash $ORCHESTRATOR_PATH/Guardian/set_to_container.sh > /dev/null

echo "Setting application to unguarded"
for i in "${apps[@]}"
do
	status=$(bash $ORCHESTRATOR_PATH/Structures/set_to_unguarded.sh $i)
	if [ "$status" != "201" ]; then
        echo "Error $status setting app $i"
    fi
done

echo "Setting application resource [energy] to unguarded"
for i in "${apps[@]}"
do
    status=$(bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_unguarded.sh $i ${resources[@]})
    if [ "$status" != "201" ]; then
        echo "Error $status setting energy to unguarded for app $i"
    fi
done

echo "Deactivating energy rules"
for i in "${energy_rules[@]}"
do
    status=$(bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh $i)
    if [ "$status" != "201" ]; then
        echo "Error $status deactivating energy rule $i"
    fi
done
