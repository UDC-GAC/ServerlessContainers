DEV_PATH=$HOME/development
RESCALER_PATH=$DEV_PATH/automatic-rescaler
BDWACHDOG_PATH=$DEV_PATH/metrics-to-time-series
export PYTHONPATH=$RESCALER_PATH:$BDWACHDOG_PATH

tmux new -d -s "ClusterGuardian" "python ClusterGuardian/Guardian.py"
tmux new -d -s "ClusterScaler" "python ClusterRescaler/ClusterScaler.py"
