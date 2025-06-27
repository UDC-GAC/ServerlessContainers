# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

## CPU usage
cpu_exceeded_upper = dict(
    _id='cpu_exceeded_upper',
    type='rule',
    resource="cpu",
    name='cpu_exceeded_upper',
    rule=dict(
        {"and": [
            {">": [
                {"var": "cpu.structure.cpu.usage"},
                {"var": "cpu.limits.cpu.upper"}]},
            {"<": [
                {"var": "cpu.limits.cpu.upper"},
                {"var": "cpu.structure.cpu.max"}]},
            {"<": [
                {"var": "cpu.structure.cpu.current"},
                {"var": "cpu.structure.cpu.max"}]}
        ]
        }),
    generates="events",
    action={"events": {"scale": {"up": 1}}},
    active=True
)

cpu_dropped_lower = dict(
    _id='cpu_dropped_lower',
    type='rule',
    resource="cpu",
    name='cpu_dropped_lower',
    rule=dict(
        {"and": [
            {">": [
                {"var": "cpu.structure.cpu.usage"},
                0]},
            {"<": [
                {"var": "cpu.structure.cpu.usage"},
                {"var": "cpu.limits.cpu.lower"}]},
            {">": [
                {"var": "cpu.limits.cpu.lower"},
                {"var": "cpu.structure.cpu.min"}]}]}),
    generates="events",
    action={"events": {"scale": {"down": 1}}},
    active=True
)

# Avoid hysteresis by only rescaling when X underuse events and no bottlenecks are detected, or viceversa
CpuRescaleUp = dict(
    _id='CpuRescaleUp',
    type='rule',
    resource="cpu",
    name='CpuRescaleUp',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.up"},
                2]},
            {"<=": [
                {"var": "events.scale.down"},
                2]}
        ]}),
    events_to_remove=2,
    generates="requests",
    action={"requests": ["CpuRescaleUp"]},
    amount=75,
    rescale_policy="amount",
    rescale_type="up",
    active=True
)

CpuRescaleDown = dict(
    _id='CpuRescaleDown',
    type='rule',
    resource="cpu",
    name='CpuRescaleDown',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.down"},
                6]},
            {"<=": [
                {"var": "events.scale.up"},
                0]}
        ]}),
    events_to_remove=6,
    generates="requests",
    action={"requests": ["CpuRescaleDown"]},
    rescale_policy="fit_to_usage",
    rescale_type="down",
    active=True,
)

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
    active=False,
    generates="",
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
    active=False,
    generates="",
)

## Memory
mem_exceeded_upper = dict(
    _id='mem_exceeded_upper',
    type='rule',
    resource="mem",
    name='mem_exceeded_upper',
    rule=dict(
        {"and": [
            {">": [
                {"var": "mem.structure.mem.usage"},
                {"var": "mem.limits.mem.upper"}]},
            {"<": [
                {"var": "mem.limits.mem.upper"},
                {"var": "mem.structure.mem.max"}]},
            {"<": [
                {"var": "mem.structure.mem.current"},
                {"var": "mem.structure.mem.max"}]}

        ]
        }),
    generates="events",
    action={"events": {"scale": {"up": 1}}},
    active=True
)

mem_dropped_lower = dict(
    _id='mem_dropped_lower',
    type='rule',
    resource="mem",
    name='mem_dropped_lower',
    rule=dict(
        {"and": [
            {">": [
                {"var": "mem.structure.mem.usage"},
                0]},
            {"<": [
                {"var": "mem.structure.mem.usage"},
                {"var": "mem.limits.mem.lower"}]},
            {">": [
                {"var": "mem.limits.mem.lower"},
                {"var": "mem.structure.mem.min"}]}]}),
    generates="events",
    action={"events": {"scale": {"down": 1}}},
    active=True
)

MemRescaleUp = dict(
    _id='MemRescaleUp',
    type='rule',
    resource="mem",
    name='MemRescaleUp',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.up"},
                2]},
            {"<=": [
                {"var": "events.scale.down"},
                6]}
        ]}),
    generates="requests",
    events_to_remove=2,
    action={"requests": ["MemRescaleUp"]},
    amount=256,
    rescale_policy="amount",
    rescale_type="up",
    active=True
)

MemRescaleDown = dict(
    _id='MemRescaleDown',
    type='rule',
    resource="mem",
    name='MemRescaleDown',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.down"},
                8]},
            {"<=": [
                {"var": "events.scale.up"},
                0]}
        ]}),
    generates="requests",
    events_to_remove=8,
    action={"requests": ["MemRescaleDown"]},
    rescale_policy="fit_to_usage",
    rescale_type="down",
    active=True
)

## Disk READ
disk_read_exceeded_upper = dict(
    _id='disk_read_exceeded_upper',
    type='rule',
    resource="disk_read",
    name='disk_read_exceeded_upper',
    rule=dict(
        {"and": [
            {">": [
                {"var": "disk_read.structure.disk_read.usage"},
                {"var": "disk_read.limits.disk_read.upper"}]},
            {"<": [
                {"var": "disk_read.limits.disk_read.upper"},
                {"var": "disk_read.structure.disk_read.max"}]},
            {"<": [
                {"var": "disk_read.structure.disk_read.current"},
                {"var": "disk_read.structure.disk_read.max"}]}

        ]
        }),
    generates="events",
    action={"events": {"scale": {"up": 1}}},
    active=True
)

disk_read_dropped_lower = dict(
    _id='disk_read_dropped_lower',
    type='rule',
    resource="disk_read",
    name='disk_read_dropped_lower',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "disk_read.structure.disk_read.usage"},
                0]},
            {"<": [
                {"var": "disk_read.structure.disk_read.usage"},
                {"var": "disk_read.limits.disk_read.lower"}]},
            {">": [
                {"var": "disk_read.limits.disk_read.lower"},
                {"var": "disk_read.structure.disk_read.min"}]}]}),
    generates="events",
    action={"events": {"scale": {"down": 1}}},
    active=True
)

Disk_readRescaleUp = dict(
    _id='Disk_readRescaleUp',
    type='rule',
    resource="disk_read",
    name='Disk_readRescaleUp',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.up"},
                1]},
            {"<=": [
                {"var": "events.scale.down"},
                6]}
        ]}),
    generates="requests",
    events_to_remove=1,
    action={"requests": ["Disk_readRescaleUp"]},
    amount=450,
    rescale_policy="amount",
    rescale_type="up",
    active=True
)

Disk_readRescaleDown = dict(
    _id='Disk_readRescaleDown',
    type='rule',
    resource="disk_read",
    name='Disk_readRescaleDown',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.down"},
                6]},
            {"<=": [
                {"var": "events.scale.up"},
                0]}
        ]}),
    generates="requests",
    events_to_remove=6,
    action={"requests": ["Disk_readRescaleDown"]},
    rescale_policy="fit_to_usage",
    rescale_type="down",
    active=True
)


## Disk WRITE
disk_write_exceeded_upper = dict(
    _id='disk_write_exceeded_upper',
    type='rule',
    resource="disk_write",
    name='disk_write_exceeded_upper',
    rule=dict(
        {"and": [
            {">": [
                {"var": "disk_write.structure.disk_write.usage"},
                {"var": "disk_write.limits.disk_write.upper"}]},
            {"<": [
                {"var": "disk_write.limits.disk_write.upper"},
                {"var": "disk_write.structure.disk_write.max"}]},
            {"<": [
                {"var": "disk_write.structure.disk_write.current"},
                {"var": "disk_write.structure.disk_write.max"}]}

        ]
        }),
    generates="events",
    action={"events": {"scale": {"up": 1}}},
    active=True
)

disk_write_dropped_lower = dict(
    _id='disk_write_dropped_lower',
    type='rule',
    resource="disk_write",
    name='disk_write_dropped_lower',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "disk_write.structure.disk_write.usage"},
                0]},
            {"<": [
                {"var": "disk_write.structure.disk_write.usage"},
                {"var": "disk_write.limits.disk_write.lower"}]},
            {">": [
                {"var": "disk_write.limits.disk_write.lower"},
                {"var": "disk_write.structure.disk_write.min"}]}]}),
    generates="events",
    action={"events": {"scale": {"down": 1}}},
    active=True
)

Disk_writeRescaleUp = dict(
    _id='Disk_writeRescaleUp',
    type='rule',
    resource="disk_write",
    name='Disk_writeRescaleUp',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.up"},
                1]},
            {"<=": [
                {"var": "events.scale.down"},
                6]}
        ]}),
    generates="requests",
    events_to_remove=1,
    action={"requests": ["Disk_writeRescaleUp"]},
    amount=450,
    rescale_policy="amount",
    rescale_type="up",
    active=True
)

Disk_writeRescaleDown = dict(
    _id='Disk_writeRescaleDown',
    type='rule',
    resource="disk_write",
    name='Disk_writeRescaleDown',
    rule=dict(
        {"and": [
            {">=": [
                {"var": "events.scale.down"},
                6]},
            {"<=": [
                {"var": "events.scale.up"},
                0]}
        ]}),
    generates="requests",
    events_to_remove=6,
    action={"requests": ["Disk_writeRescaleDown"]},
    rescale_policy="fit_to_usage",
    rescale_type="down",
    active=True
)

## Energy usage
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
    active=True
)

energy_dropped_lower_and_cpu_exceeded_upper = dict(
    _id='energy_dropped_lower_and_cpu_exceeded_upper',
    type='rule',
    resource="energy",
    name='energy_dropped_lower_and_cpu_exceeded_upper',
    rule=dict(
        {"and": [
            {"<": [
                {"var": "energy.structure.energy.usage"},
                {"var": "energy.limits.energy.upper"}]},
            {">": [
                {"var": "cpu.structure.cpu.usage"},
                {"var": "cpu.limits.cpu.upper"}]}]}),
    generates="events", action={"events": {"scale": {"down": 1}}},
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
    rescale_policy="proportional",
    rescale_type="up",
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
    rescale_policy="proportional",
    rescale_type="down",
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
        
        # CPU
        handler.add_rule(cpu_exceeded_upper)
        handler.add_rule(cpu_dropped_lower)
        handler.add_rule(CpuRescaleUp)
        handler.add_rule(CpuRescaleDown)
        handler.add_rule(cpu_usage_high)
        handler.add_rule(cpu_usage_low)

        # Memory
        handler.add_rule(mem_exceeded_upper)
        handler.add_rule(mem_dropped_lower)
        handler.add_rule(MemRescaleUp)
        handler.add_rule(MemRescaleDown)

        ## Disk
        # Read
        handler.add_rule(disk_read_exceeded_upper)
        handler.add_rule(disk_read_dropped_lower)
        handler.add_rule(Disk_readRescaleUp)
        handler.add_rule(Disk_readRescaleDown)
        # Write
        handler.add_rule(disk_write_exceeded_upper)
        handler.add_rule(disk_write_dropped_lower)
        handler.add_rule(Disk_writeRescaleUp)
        handler.add_rule(Disk_writeRescaleDown)

        # Energy
        handler.add_rule(energy_exceeded_upper)
        handler.add_rule(energy_dropped_lower_and_cpu_exceeded_upper)
        handler.add_rule(EnergyRescaleUp)
        handler.add_rule(EnergyRescaleDown)

