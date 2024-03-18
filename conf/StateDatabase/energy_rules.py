# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

energy_exceeded_upper = dict(
    _id='energy_exceeded_upper',
    type='rule',
    resource="energy",
    name='energy_exceeded_upper',
    rule=dict(
        {"and": [
            {">": [
                {"var": "energy.structure.energy.usage"},
                {"var": "energy.structure.energy.max"}]}]}),
    generates="events", action={"events": {"scale": {"up": 1}}},
    active=False
)

EnergyRescaleDown = dict(
    _id='EnergyRescaleDown',
    type='rule',
    resource="energy",
    name='EnergyRescaleDown',
    rule=dict(
        {"and": [
            {"<=": [
                {"var": "events.scale.down"},
                1]},
            {">=": [
                {"var": "events.scale.up"},
                4]}
        ]}),
    generates="requests",
    events_to_remove=4,
    action={"requests": ["CpuRescaleDown"]},
    amount=-20,
    rescale_by="proportional",
    rescale_type="down",
    active=False
)

energy_dropped_lower = dict(
    _id='energy_dropped_lower',
    type='rule',
    resource="energy",
    name='energy_dropped_lower',
    rule=dict(
        {"and": [
            {"<": [
                {"var": "energy.structure.energy.usage"},
                {"var": "energy.structure.energy.max"}]}]}),
    generates="events", action={"events": {"scale": {"down": 1}}},
    active=False
)

EnergyRescaleUp = dict(
    _id='EnergyRescaleUp',
    type='rule',
    resource="energy",
    name='EnergyRescaleUp',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.down"},
                3]},
            {"<=": [
                {"var": "events.scale.up"},
                1]}
        ]}),
    generates="requests",
    events_to_remove=3,
    action={"requests": ["CpuRescaleUp"]},
    amount=20,
    rescale_by="proportional",
    rescale_type="up",
    active=False
)


if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    if handler.database_exists("rules"):
        print("Adding 'energy rules' documents")
        handler.add_rule(energy_exceeded_upper)
        handler.add_rule(EnergyRescaleDown)
        handler.add_rule(energy_dropped_lower)
        handler.add_rule(EnergyRescaleUp)
