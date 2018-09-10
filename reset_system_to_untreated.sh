#!/usr/bin/env bash
DEV_PATH=$HOME/development
export RESCALER_PATH=$DEV_PATH/automatic-rescaler

echo "Setting container resources"
bash $RESCALER_PATH/NodeRescaler/config/small-limit/update_all.sh

echo "Resetting host resources accounting"
python $RESCALER_PATH/StateDatabase/initializers/reset_host_structure_info.py

bash $RESCALER_PATH/Orchestrator/Guardian/set_to_container.sh


echo "Setting application to unguarded"
bash $RESCALER_PATH/Orchestrator/Structures/set_to_unguarded.sh app1

echo "Setting container nodes to unguarded"
bash $RESCALER_PATH/Orchestrator/Structures/set_to_unguarded.sh node0
bash $RESCALER_PATH/Orchestrator/Structures/set_to_unguarded.sh node1
bash $RESCALER_PATH/Orchestrator/Structures/set_to_unguarded.sh node2
bash $RESCALER_PATH/Orchestrator/Structures/set_to_unguarded.sh node3
bash $RESCALER_PATH/Orchestrator/Structures/set_to_unguarded.sh node4
bash $RESCALER_PATH/Orchestrator/Structures/set_to_unguarded.sh node5

echo "Setting application resources [cpu,mem,disk,net,energy] to unguarded"
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node0 cpu
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node0 mem
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node0 disk
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node0 net
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node0 energy
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node1 cpu
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node1 mem
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node1 disk
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node1 net
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node1 energy
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node2 cpu
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node2 mem
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node2 disk
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node2 net
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node2 energy
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node3 cpu
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node3 mem
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node3 disk
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node3 net
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node3 energy
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node4 cpu
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node4 mem
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node4 disk
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node4 net
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node4 energy
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node5 cpu
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node5 mem
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node5 disk
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node5 net
bash $RESCALER_PATH/Orchestrator/Structures/set_resource_to_unguarded.sh node5 energy

echo "Deactivating energy rules"
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh EnergyRescaleDown
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh EnergyRescaleUp
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh energy_dropped_lower
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh energy_exceeded_upper

echo "Deactivating rescaling rules"
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh CpuRescaleDown
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh CpuRescaleUp
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh MemRescaleDown
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh MemRescaleUp

bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh cpu_dropped_lower
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh cpu_exceeded_upper
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh mem_dropped_lower
bash $RESCALER_PATH/Orchestrator/Rules/deactivate_rule.sh mem_exceeded_upper
