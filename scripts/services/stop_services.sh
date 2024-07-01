#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

declare -a serviceArr=("guardian" "scaler" "orchestrator" "refeeder" "sanity_checker" "structure_snapshoter" "database_snapshoter" "watt_wizard" "watt_trainer")

## now loop through the above array
for s in "${serviceArr[@]}"
do
  tmux has-session -t "${s}" 2>/dev/null
  if [ $? != 0 ]; then
    echo "Service '${s}' is not running"
  else
    echo "Stopping ${s}"
    tmux kill-session -t "${s}"
  fi
done


