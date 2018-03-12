RESCALER_PATH=$HOME/Desktop/development/automatic-rescaler
export PYTHONPATH=$RESCALER_PATH

tmux new -d -s "NodeRescaler" "python Rescaler/NodeRescaler.py"
