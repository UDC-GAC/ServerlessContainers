#!/usr/bin/env bash
# Set the power budget (energy 'max') of a container, application or user through the Orchestrator.
#
# The Orchestrator notifies the EnergyManager (STATE_UPDATE), which applies it in its next iteration (~1 s):
#   - application/user: the budget is propagated to its applications/containers;
#   - container: its application (and user) budget changes by the same amount, so the tree stays consistent.
# The EnergyManager writes the new container budgets to CouchDB ('max' and 'current'), NodeRescaler (energy_limit)
# and the host free energy.
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
source "${scriptDir}/../set_env.sh"

if [ -z "$3" ]
then
      echo "3 arguments are needed"
      echo "1 -> structure type: container, application or user"
      echo "2 -> structure name (e.g., compute-2-5-cont0, npb_is, user0)"
      echo "3 -> power budget in W (e.g., 30)"
      exit 1
fi

TYPE="$1"
NAME="$2"
BUDGET="$3"

case "${TYPE}" in
  container|application) URL="http://${ORCHESTRATOR_REST_URL}/structure/${NAME}" ;;
  user) URL="http://${ORCHESTRATOR_REST_URL}/user/${NAME}" ;;
  *) echo "Invalid structure type '${TYPE}' (use container, application or user)"; exit 1 ;;
esac

if ! [[ "${BUDGET}" =~ ^[0-9]+$ ]]; then
  echo "Power budget must be a non-negative integer (W), got '${BUDGET}'"
  exit 1
fi

# Current energy values of the structure (the budget cannot be lower than its 'min')
STRUCTURE=$(curl -s -f "${URL}") || { echo "Structure '${NAME}' not found"; exit 1; }
read -r CURRENT_MAX CURRENT_MIN <<< "$(python3 -c '
import json, sys
energy = json.load(sys.stdin).get("resources", {}).get("energy", {})
print(energy.get("max", "none"), energy.get("min", 0))' <<< "${STRUCTURE}")"
if [ "${CURRENT_MAX}" == "none" ]; then
  echo "Structure '${NAME}' has no energy resource"
  exit 1
fi
if [ "${BUDGET}" -lt "${CURRENT_MIN}" ]; then
  echo "Power budget ${BUDGET} W is lower than the energy 'min' of '${NAME}' (${CURRENT_MIN} W)"
  exit 1
fi

# Without the EnergyManager, EnergyController + Scaler do not propagate application/user budgets to containers
EM_ACTIVE=$(curl -s "http://${ORCHESTRATOR_REST_URL}/service/energy_manager" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("config", {}).get("ACTIVE", False))
except Exception:
    print(False)')
if [ "${EM_ACTIVE}" != "True" ]; then
  echo "WARNING: the EnergyManager is not active, the budget is only changed in CouchDB"
fi

curl -s -f -X PUT -H "Content-Type: application/json" "${URL}/resources/energy/max" -d '{"value":"'"${BUDGET}"'"}' > /dev/null \
  || { echo "Failed to set the power budget of '${NAME}'"; exit 1; }
echo "Power budget of ${TYPE} '${NAME}': ${CURRENT_MAX} -> ${BUDGET} W"
