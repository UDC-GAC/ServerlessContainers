tmux kill-session -t "Orchestrator"
kill $(ps aux | grep "[g]unicorn --bind 0.0.0.0:5000" | awk '{print $2}')
tmux kill-session -t "Guardian"
tmux kill-session -t "Refeeder"
tmux kill-session -t "DatabaseSnapshoter"

