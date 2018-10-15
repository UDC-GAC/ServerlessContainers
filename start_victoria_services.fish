cd /home/jonatan/development/automatic-rescaler/
#tmux new -d -s "Orchestrator" "source set_pythonpath.fish; python Orchestrator/Orchestrator.py 2> orchestrator.log"
tmux new -d -s "Orchestrator" "source set_pythonpath.sh; cd $RESCALER_PATH/Orchestrator; gunicorn --bind 0.0.0.0:5000 wsgi:app -w 2 --threads 2"
tmux new -d -s "Guardian" "source set_pythonpath.fish; python Guardian/Guardian.py"
tmux new -d -s "Refeeder" "source set_pythonpath.fish; python Refeeder/Refeeder.py"
tmux new -d -s "DatabaseSnapshoter" "source set_pythonpath.fish; python Snapshoters/DatabaseSnapshoter.py"

