# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

# This rule is used by the ReBalancer, NOT the Guardian, leave it deactivated
cpu_usage_low = dict(
    _id='cpu_usage_low',
    type='rule',
    resource="cpu",
    name='cpu_usage_low',
    rule=dict(
        {"and": [
            {">=": [
                {"-": [
                    {"var": "cpu.structure.cpu.current"},
                    {"var": "cpu.structure.cpu.min"}]
                },
                25
            ]},
            {"<": [
                {"/": [
                    {"var": "cpu.structure.cpu.usage"},
                    {"var": "cpu.structure.cpu.current"}]
                },
                0.4
            ]}
        ]}
    ),
    active=False
)

# This rule is used by the ReBalancer, NOT the Guardian, leave it deactivated
cpu_usage_high = dict(
    _id='cpu_usage_high',
    type='rule',
    resource="cpu",
    name='cpu_usage_high',
    rule=dict(
        {"and": [
            {">=": [
                {"-": [
                    {"var": "cpu.structure.cpu.max"},
                    {"var": "cpu.structure.cpu.current"}]
                },
                25
            ]},
            {">": [
                {"/": [
                    {"var": "cpu.structure.cpu.usage"},
                    {"var": "cpu.structure.cpu.current"}]
                },
                0.7
            ]}
        ]}
    ),
    active=False
)

# This rule is activated when the energy used is above the maximum allowed
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
    generates="events", action={"events": {"scale": {"down": 1}}},
    active=True
)
EnergyRescaleDown = dict(
    _id='EnergyRescaleDown',
    type='rule',
    resource="energy",
    name='EnergyRescaleDown',
    rule=dict(
        {"and": [
            {"<=": [
                {"var": "events.scale.up"},
                1]},
            {">=": [
                {"var": "events.scale.down"},
                3]}
        ]}),
    generates="requests",
    events_to_remove=3,
    action={"requests": ["CpuRescaleDown"]},
    amount=-20,
    rescale_by="proportional",
    active=True
)

# This rule is activated when the energy used is below the maximum allowed AND
# the CPU usage is above 90% of the CPU limit (i.e., The structure is getting close to a CPU bottleneck)
# If the structure has a high CPU limit and low energy usage it may be because either it requires internal
# CPU Rebalance or plainly, it is idle.
energy_dropped_lower = dict(
    _id='energy_dropped_lower',
    type='rule',
    resource="energy",
    name='energy_dropped_lower',
    rule=dict(
        {"and": [
            {"<": [
                {"var": "energy.structure.energy.usage"},
                {"var": "energy.structure.energy.max"}]},

            {">": [
                {"/": [
                    {"var": "cpu.structure.cpu.usage"},
                    {"var": "cpu.structure.cpu.current"}]
                },
                0.9
            ]}
        ]}),
    generates="events", action={"events": {"scale": {"up": 1}}},
    active=True
)
EnergyRescaleUp = dict(
    _id='EnergyRescaleUp',
    type='rule',
    resource="energy",
    name='EnergyRescaleUp',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.up"},
                3]},
            {"<=": [
                {"var": "events.scale.down"},
                1]}
        ]}),
    generates="requests",
    events_to_remove=3,
    action={"requests": ["CpuRescaleUp"]},
    amount=20,
    rescale_by="proportional",
    active=True
)

if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "rules"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)
    if handler.database_exists("rules"):
        print("Adding 'rules' documents")
        handler.add_rule(energy_exceeded_upper)
        handler.add_rule(energy_dropped_lower)
        handler.add_rule(EnergyRescaleDown)
        handler.add_rule(EnergyRescaleUp)
        handler.add_rule(cpu_usage_low)
        handler.add_rule(cpu_usage_high)
