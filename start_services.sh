RESCALER_PATH=$HOME/Desktop/development/automatic-rescaler
BDWACHDOG_PATH=$HOME/Desktop/development/metrics-to-time-series
export PYTHONPATH=$RESCALER_PATH:$BDWACHDOG_PATH

tmux new -d -s "ClusterGuardian" "python ClusterGuardian/Guardian.py"
tmux new -d -s "ClusterScaler" "python Rescaler/ClusterScaler.py"
tmux new -d -s "DatabaseSnapshoter" "python Snapshoters/StateDatabaseSnapshoter.py"
tmux new -d -s "NodeSnapshoter" "python Snapshoters/NodeStateSnapshoter.py"
