tmux new -d -s "DatabaseSnapshoter" "bash persistDatabase.sh"
tmux new -d -s "NodeSnapshoter" "bash persistNode.sh"
