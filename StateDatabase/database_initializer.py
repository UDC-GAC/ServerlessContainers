# /usr/bin/python
import StateDatabase.couchDB as couchDB
import requests


def initialize():
    databases = ['structures', 'limits', 'events', 'rules', 'requests', 'services']

    handler = couchDB.CouchDBServer()

    def create_all_dbs():
        print ("Creating all databases")
        for database in databases:
            if handler.create_database(database):
                print("Database " + database + " created")

    def remove_all_dbs():
        print ("Removing all databases")
        for database in databases:
            try:
                if handler.remove_database(database):
                    print("Database " + database + " removed")
            except requests.exceptions.HTTPError:
                pass

    remove_all_dbs()
    create_all_dbs()

    containers = ["node0", "node1", "node2", "node3"]
    hosts = ["es-udc-dec-jonatan-dante", "es-udc-dec-jonatan-apolo"]
    applications = ["app1"]
    # CREATE LIMITS
    if handler.database_exists("limits"):
        print ("Adding 'limits' documents")
        for c in containers:
            container = dict(
                type='limit',
                name=c,
                resources=dict(
                    cpu=dict(upper=170, lower=150, boundary=20),
                    mem=dict(upper=8000, lower=7000, boundary=1000),
                    disk=dict(upper=100, lower=100, boundary=10),
                    net=dict(upper=100, lower=100, boundary=10),
                    energy=dict(upper=15, lower=5, boundary=3)
                )
            )
            handler.add_limit(container)

        application = dict(
            type='limit',
            name='app1',
            resources=dict(
                cpu=dict(upper=300, lower=100, boundary=50),
                mem=dict(upper=14000, lower=2000, boundary=4000),
                disk=dict(upper=100, lower=100, boundary=10),
                net=dict(upper=100, lower=100, boundary=10),
                energy=dict(upper=50, lower=5, boundary=5)
            )
        )
        handler.add_limit(application)

    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print ("Adding 'structures' documents")
        for c in containers:
            container = dict(
                type='structure',
                subtype='container',
                host='es-udc-dec-jonatan-dante',
                name=c,
                guard=True,
                resources=dict(
                    cpu=dict(max=200, min=10),
                    mem=dict(max=8192, min=256),
                    disk=dict(max=100, min=100),
                    net=dict(max=100, min=100),
                    energy=dict(max=20, min=0)
                )
            )
            handler.add_structure(container)

        for h in hosts:
            host = dict(
                type='structure',
                subtype='host',
                name=h,
                host=h,
                resources=dict(
                    cpu=dict(max=800),
                    mem=dict(max=46000)
                )
            )
            handler.add_structure(host)

        app = dict(
            type='structure',
            subtype='application',
            name="app1",
            guard=True,
            resources=dict(
                cpu=dict(max=800, min=40),
                mem=dict(max=46000, min=1024),
                energy=dict(max=60, min=0)
            ),
            containers=["node0","node1","node2","node3"]
        )
        handler.add_structure(app)
    # CREATE RULES
    if handler.database_exists("rules"):
        print ("Adding 'rules' documents")

        # CPU
        cpu_exceeded_upper = dict(
            _id='cpu_exceeded_upper',
            type='rule',
            resource="cpu",
            name='cpu_exceeded_upper',
            rule=dict(
                {"and": [
                    {">": [
                        {"var": "structure.cpu.usage"},
                        {"var": "limits.cpu.upper"}]},
                    {"<": [
                        {"var": "limits.cpu.upper"},
                        {"var": "structure.cpu.max"}]},
                    {"<": [
                        {"var": "structure.cpu.current"},
                        {"var": "structure.cpu.max"}]}
                    ]
                }),
            generates="events", action={"events": {"scale": {"up": 1}}},
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
                        {"var": "structure.cpu.usage"},
                        0]},
                    {"<": [
                        {"var": "structure.cpu.usage"},
                        {"var": "limits.cpu.lower"}]},
                    {">": [
                        {"var": "limits.cpu.lower"},
                        {"var": "structure.cpu.min"}]}]}),
            generates="events",
            action={"events": {"scale": {"down": 1}}},
            active=True
        )

        handler.add_rule(cpu_exceeded_upper)
        handler.add_rule(cpu_dropped_lower)

        # Avoid hysteresis by only rescaling when X underuse events and no bottlenecks are detected, or viceversa
        CpuRescaleUp = dict(
            _id='CpuRescaleUp',
            type='rule',
            resource="cpu",
            name='CpuRescaleUp',
            rule=dict(
                {"and": [
                    {">": [
                        {"var": "events.scale.up"},
                        3]},
                    {"==": [
                        {"var": "events.scale.down"},
                        0]}
                ]}),
            events_to_remove=3,
            generates="requests",
            action={"requests": ["CpuRescaleUp"]},
            amount=20,
            rescale_by="amount",
            active=True
        )

        CpuRescaleDown = dict(
            _id='CpuRescaleDown',
            type='rule',
            resource="cpu",
            name='CpuRescaleDown',
            rule=dict(
                {"and": [
                    {">": [
                        {"var": "events.scale.down"},
                        3]},
                    {"==": [
                        {"var": "events.scale.up"},
                        0]}
                ]}),
            events_to_remove=3,
            generates="requests",
            action={"requests": ["CpuRescaleDown"]},
            amount=-20,
            rescale_by="fit_to_usage",
            active=True,
        )

        handler.add_rule(CpuRescaleUp)
        handler.add_rule(CpuRescaleDown)

        # MEM
        mem_exceeded_upper = dict(
            _id='mem_exceeded_upper',
            type='rule',
            resource="mem",
            name='mem_exceeded_upper',
            rule=dict(
                {"and": [
                    {">": [
                        {"var": "structure.mem.usage"},
                        {"var": "limits.mem.upper"}]},
                    {"<": [
                        {"var": "limits.mem.upper"},
                        {"var": "structure.mem.max"}]},
                    {"<": [
                        {"var": "structure.mem.current"},
                        {"var": "structure.mem.max"}]}

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
                        {"var": "structure.mem.usage"},
                        0]},
                    {"<": [
                        {"var": "structure.mem.usage"},
                        {"var": "limits.mem.lower"}]},
                    {">": [
                        {"var": "limits.mem.lower"},
                        {"var": "structure.mem.min"}]}]}),
            generates="events",
            action={"events": {"scale": {"down": 1}}},
            active=True
        )

        handler.add_rule(mem_exceeded_upper)
        handler.add_rule(mem_dropped_lower)

        MemRescaleUp = dict(
            _id='MemRescaleUp',
            type='rule',
            resource="mem",
            name='MemRescaleUp',
            rule=dict(
                {">": [
                    {"var": "events.scale.up"},
                    2]}),
            generates="requests",
            events_to_remove=2,
            action={"requests": ["MemRescaleUp"]},
            amount=1024,
            rescale_by="amount",
            active=True
        )

        MemRescaleDown = dict(
            _id='MemRescaleDown',
            type='rule',
            resource="mem",
            name='MemRescaleDown',
            rule=dict(
                {">": [
                    {"var": "events.scale.down"},
                    3]}),
            generates="requests",
            events_to_remove=3,
            action={"requests": ["MemRescaleDown"]},
            amount=-512,
            percentage_reduction=50,
            rescale_by="fit_to_usage",
            active=True
        )

        handler.add_rule(MemRescaleUp)
        handler.add_rule(MemRescaleDown)

        # ENERGY
        energy_exceeded_upper = dict(
            _id='energy_exceeded_upper',
            type='rule',
            resource="energy",
            name='energy_exceeded_upper',
            rule=dict(
                {"and": [
                    {">": [
                        {"var": "structure.energy.current"},
                        {"var": "structure.energy.max"}]}]}),
            generates="events", action={"events": {"scale": {"up": 1}}},
            active=True
        )
        handler.add_rule(energy_exceeded_upper)

    # CREATE SERVICES
    if handler.database_exists("services"):
        print ("Adding 'services' document")

        guardian = dict(
            name="guardian",
            type="service",
            heartbeat="",
            config=dict(
                GUARD_POLICY="serverless",
                STRUCTURE_GUARDED="container",
                WINDOW_TIMELAPSE=10,
                WINDOW_DELAY=20,
                EVENT_TIMEOUT=40,
                DEBUG=True
            )
        )

        scaler = dict(
            name="scaler",
            type="service",
            heartbeat="",
            config=dict(
                DEBUG=True,
                POLLING_FREQUENCY=5,
                REQUEST_TIMEOUT=30
            )
        )

        database_snapshoter = dict(
            name="database_snapshoter",
            type="service",
            heartbeat="",
            config=dict(
                POLLING_FREQUENCY=3,
                DEBUG=True
            )
        )

        node_state_snapshoter = dict(
            name="structures_snapshoter",
            type="service",
            heartbeat="",
            config=dict(
                POLLING_FREQUENCY=5
            )
        )

        refeeder = dict(
            name="refeeder",
            type="service",
            heartbeat="",
            config=dict(
                POLLING_FREQUENCY=5,
                WINDOW_TIMELAPSE=5,
                WINDOW_DELAY=20,
                DEBUG=True
            )
        )

        handler.add_service(scaler)
        handler.add_service(guardian)
        handler.add_service(database_snapshoter)
        handler.add_service(node_state_snapshoter)
        handler.add_service(refeeder)


initialize()
