curl -X POST 'http://couchdb:5984/services/_find' -H "Content-Type: application/json" -d '{"selector":{}, "fields":["name","heartbeat"]}'
