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
        cpu=dict(max=700, min=100, guard=False),
        mem=dict(max=46080, min=1024, guard=False),
        disk=dict(max=100, min=20, guard=False),
        net=dict(max=200, min=100, guard=False),
        energy=dict(max=20, min=0, guard=False)
    )
)


def add_containers(handler):
    containers = [("master0", "host7"), ("master1", "host7"),
                  ("hibench0", "host7"), ("hibench1", "host7"),("slave9", "host7"),("kafka0", "host7"),
                  ("kafka1", "host8"), ("slave0", "host8"), ("slave1", "host8"), ("slave2", "host8"),
                  ("kafka2", "host9"), ("slave3", "host9"), ("slave4", "host9"), ("slave5", "host9"),
                  ("kafka3", "host10"), ("slave6", "host10"), ("slave7", "host10"), ("slave8", "host10")]

    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print("Adding 'structure container' documents")
        for (c, h) in containers:
            container = dict(base_container)
            container["name"] = c
            container["host"] = h
            container["host_rescaler_ip"] = h
            handler.add_structure(container)
