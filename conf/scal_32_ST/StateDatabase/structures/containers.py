# /usr/bin/python
base_container = dict(
    type='structure',
    subtype='container',
    guard_policy="serverless",
    host='host0',
    host_rescaler_ip='host0',
    host_rescaler_port='8000',
    name="base_container",
    guard=False,
    resources=dict(
        cpu=dict(max=600, min=50, guard=True),
        mem=dict(max=46080, min=1024, guard=False),
        disk=dict(max=100, min=20, guard=False),
        net=dict(max=200, min=100, guard=False),
        energy=dict(max=20, min=0, guard=False)
    )
)


def add_containers(handler):
    containers = [("hibench0", "host28"), ("hibench1", "host28"), ("slave9", "host28"), ("kafka0", "host28"),
                  ("kafka1", "host29"), ("slave0", "host29"), ("slave1", "host29"), ("slave2", "host29"),
                  ("kafka2", "host30"), ("slave3", "host30"), ("slave4", "host30"), ("slave5", "host30"),
                  ("kafka3", "host31"), ("slave6", "host31"), ("slave7", "host31"), ("slave8", "host31"),
                  ("kafka4", "host32"), ("hibench2", "host32"), ("hibench3", "host32"), ("slave19", "host32"),
                  ("kafka5", "host33"), ("slave10", "host33"), ("slave11", "host33"), ("slave12", "host33"),
                  ("kafka6", "host34"), ("slave13", "host34"), ("slave14", "host34"), ("slave15", "host34"),
                  ("kafka7", "host35"), ("slave16", "host35"), ("slave17", "host35"), ("slave18", "host35")]

    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print("Adding 'structure container' documents")
        for (c, h) in containers:
            container = dict(base_container)
            container["name"] = c
            container["host"] = h
            container["host_rescaler_ip"] = h
            handler.add_structure(container)
