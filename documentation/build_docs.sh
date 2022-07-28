#!/usr/bin/env bash
rm -Rf web
mkdir -p web
mkdocs build -d web
bash build_code_doc.sh