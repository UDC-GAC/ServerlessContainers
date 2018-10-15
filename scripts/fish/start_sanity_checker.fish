#!/usr/bin/env bash
tmux new -d -s "SanityChecker" "source set_pythonpath.fish; python SanityChecker/SanityChecker.py"

