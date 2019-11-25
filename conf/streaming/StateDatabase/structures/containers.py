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
        cpu=dict(max=600, min=100, guard=False),
        mem=dict(max=46080, min=1024, guard=False),
        disk=dict(max=100, min=20, guard=False),
        net=dict(max=200, min=100, guard=False),
        energy=dict(max=20, min=0, guard=False)
    )
)


def add_containers(handler):
    containers = [#("master0", "host24"), ("master1", "host24"),
                  ("kafka0", "host24"), ("hibench0", "host24"), ("slave0", "host24"),("slave1", "host24"),
                  ("kafka1", "host25"), ("slave2", "host25"), ("slave3", "host25"), ("slave4", "host25"),
                  ("kafka2", "host26"), ("hibench1", "host26"), ("slave5", "host26"), ("slave6", "host26"),
                  ("kafka3", "host27"), ("slave7", "host27"), ("slave8", "host27"), ("slave9", "host27")]

    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print("Adding 'structure container' documents")
        for (c, h) in containers:
            container = dict(base_container)
            container["name"] = c
            container["host"] = h
            container["host_rescaler_ip"] = h
            handler.add_structure(container)
