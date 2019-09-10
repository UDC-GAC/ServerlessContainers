#!/usr/bin/env bash
export ORCHESTRATOR_PATH=$HOME/development/ServerlessContainers/scripts/Orchestrator

nodes=( aux0 aux1 pre0 pre1 pre2 pre3 comp0 comp1 comp2 comp3 comp4 comp5 comp6 comp7 comp8 comp9 )
apps=( aux_user0 pre_user0 comp_user0 )
resources=( energy )
energy_rules=( EnergyRescaleDown EnergyRescaleUp energy_dropped_lower energy_exceeded_upper )

echo "Setting Guardian to guard containers"
bash $ORCHESTRATOR_PATH/Guardian/set_to_container.sh > /dev/null

#echo "Setting applications to unguarded"
#for i in "${apps[@]}"
#do
#	status=$(bash $ORCHESTRATOR_PATH/Structures/set_to_unguarded.sh $i)
#	if [ "$status" != "201" ]; then
#        echo "Error $status setting app $i"
#    fi
#done

#echo "Setting application resource [energy] to unguarded"
#for i in "${apps[@]}"
#do
#    status=$(bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_unguarded.sh $i ${resources[@]})
#    if [ "$status" != "201" ]; then
#        echo "Error $status setting energy to unguarded for app $i"
#    fi
#done

#echo "Deactivating energy rules"
#for i in "${energy_rules[@]}"
#do
#    status=$(bash $ORCHESTRATOR_PATH/Rules/deactivate_rule.sh $i)
#    if [ "$status" != "201" ]; then
#        echo "Error $status deactivating energy rule $i"
#    fi
#done
