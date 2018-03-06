export PYTHONUNBUFFERED="yes"
export POST_DOC_BUFFER_TIMEOUT=4
export POST_SEND_DOCS_TIMEOUT=1
python StateDatabaseSnapshoter.py | ./send_to_OpenTSDB.py
