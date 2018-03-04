ssh jonatan@dante "cd /home/jonatan/development/automatic-rescaler/NodeRescaler && gunicorn --bind 0.0.0.0:8000 wsgi:app -w 2"
