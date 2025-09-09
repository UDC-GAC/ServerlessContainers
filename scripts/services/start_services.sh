#!/usr/bin/env bash
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")



declare -a serviceArr=("guardian" "scaler" "orchestrator" "refeeder" "sanity_checker" "structure_snapshoter" "database_snapshoter" "watt_wizard" "watt_trainer" "limits_dispatcher")

## now loop through the above array
for s in "${serviceArr[@]}"
do
  tmux has-session -t "${s}" 2>/dev/null
  if [ $? == 0 ]; then
    echo "Service '${s}' already exists"
  else
    echo "Starting '${s}'"
    bash $scriptDir/${s}/start_tmux.sh
    sleep 1
    tmux has-session -t "${s}" 2>/dev/null
    if [ $? == 0 ]; then
      echo "Service '${s}' successfully spawned"
    else
      echo "Service '${s}' did not start"
    fi
  fi
done





