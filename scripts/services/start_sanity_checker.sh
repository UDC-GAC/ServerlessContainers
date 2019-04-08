#!/usr/bin/env bash
tmux new -d -s "SanityChecker" "source set_pythonpath.sh; python3 SanityChecker/SanityChecker.py"

