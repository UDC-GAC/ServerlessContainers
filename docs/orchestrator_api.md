## Services

* /service/ ['GET']
* /service/<service_name\> ['GET', 'PUT']
* /service/<service_name\>/<key\> ['PUT']


## Rules

* /rule/ ['GET']
* /rule/<rule_name\> ['GET']
* /rule/<rule_name\>/activate ['PUT']
* /rule/<rule_name\>/deactivate ['PUT']
* /rule/<rule_name\>/amount ['PUT']
* /rule/<rule_name\>/policy ['PUT']
* /rule/<rule_name\>/events_required ['PUT']


## Structures

* /structure/ ['GET']
* /structure/<structure_name\> ['GET']
* /structure/<structure_name\>/resources ['GET']
* /structure/<structure_name\>/resources/<resource\> ['GET']
* /structure/<structure_name\>/resources/<resource\>/<parameter\> ['GET', 'PUT']
* /structure/<structure_name\>/guard ['PUT']
* /structure/<structure_name\>/unguard ['PUT']
* /structure/<structure_name\>/resources/<resource\>/guard ['PUT']
* /structure/<structure_name\>/resources/<resource\>/unguard ['PUT']
* /structure/<structure_name\>/resources/guard ['PUT']
* /structure/<structure_name\>/resources/unguard ['PUT']
* /structure/<structure_name\>/limits ['GET']
* /structure/<structure_name\>/limits/<resource\> ['GET']
* /structure/<structure_name\>/limits/<resource\>/boundary ['PUT']
* /structure/container/<structure_name\>/<app_name\> ['PUT', 'DELETE']
* /structure/container/<structure_name\> ['PUT', 'DELETE']
* /structure/host/<structure_name\> ['PUT', 'DELETE']
* /structure/apps/<structure_name\> ['PUT', 'DELETE']

## Users

* /user/ ['GET']
* /user/<user_name\> ['GET']
* /user/<user_name\>/energy/max ['PUT']

## Others

* "/heartbeat ['GET']