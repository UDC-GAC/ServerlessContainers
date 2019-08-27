#!/usr/bin/env bash
export ORCHESTRATOR_PATH=$HOME/development/AutomaticRescaler/scripts/Orchestrator

nodes=( kafka0 kafka1 kafka2 kafka3 kafka4 kafka5 kafka6 kafka7 slave0 slave1 slave2 slave3 slave4 slave5 slave6 \
slave7 slave8 slave9 slave10 slave11 slave12 slave13 slave14 slave15 slave16 slave17 slave18 slave19 hibench0 \
hibench1 hibench2 hibench3 )
resources=( cpu )

echo "Setting Guardian to guard containers"
bash $ORCHESTRATOR_PATH/Guardian/set_to_container.sh > /dev/null

#echo "Setting container resources to unguarded"
#for i in "${nodes[@]}"
#do
#    bash $ORCHESTRATOR_PATH/Structures/set_many_resource_to_unguarded.sh $i ${resources[@]} > /dev/null
#done

echo "Setting container nodes to unguarded"
for i in "${nodes[@]}"
do
	bash $ORCHESTRATOR_PATH/Structures/set_to_unguarded.sh $i > /dev/null
done
