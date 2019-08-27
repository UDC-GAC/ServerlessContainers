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
        cpu=dict(max=700, min=100, guard=True),
        mem=dict(max=46080, min=1024, guard=False),
        disk=dict(max=100, min=20, guard=False),
        net=dict(max=200, min=100, guard=False),
        energy=dict(max=20, min=0, guard=False)
    )
)


def add_containers(handler):
    containers = [("master0", "host27"),
                  ("hibench0", "host27"), ("hibench1", "host27"), ("slave9", "host27"), ("kafka0", "host27"),
                  ("kafka1", "host28"), ("slave0", "host28"), ("slave1", "host28"), ("slave2", "host28"),
                  ("kafka2", "host29"), ("slave3", "host29"), ("slave4", "host29"), ("slave5", "host29"),
                  ("kafka3", "host30"), ("slave6", "host30"), ("slave7", "host30"), ("slave8", "host30"),
                  ("kafka4", "host31"), ("hibench2", "host31"), ("hibench3", "host31"), ("slave19", "host31"),
                  ("kafka5", "host32"), ("slave10", "host32"), ("slave11", "host32"), ("slave12", "host32"),
                  ("kafka6", "host33"), ("slave13", "host33"), ("slave14", "host33"), ("slave15", "host33"),
                  ("kafka7", "host34"), ("slave16", "host34"), ("slave17", "host34"), ("slave18", "host34")]

    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print("Adding 'structure container' documents")
        for (c, h) in containers:
            container = dict(base_container)
            container["name"] = c
            container["host"] = h
            container["host_rescaler_ip"] = h
            handler.add_structure(container)
