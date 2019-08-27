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
        cpu=dict(max=700, min=200, guard=False),
        mem=dict(max=46080, min=1024, guard=False),
        disk=dict(max=100, min=20, guard=False),
        net=dict(max=200, min=100, guard=False),
        energy=dict(max=20, min=0, guard=False)
    )
)


def add_containers(handler):
    containers = [  # ("master0", "host4"), ("master1", "host4"),
        ("pre0", "host4"), ("pre1", "host4"), ("pre2", "host4"), ("pre3", "host4"),
        ("comp0", "host5"), ("comp1", "host5"), ("comp2", "host5"), ("comp3", "host5"),
        ("comp4", "host6"), ("comp5", "host6"), ("comp6", "host6"), ("comp8", "host6"),
        ("comp8", "host7"), ("comp9", "host7"), ("aux0", "host7"), ("aux1", "host7")]

    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print("Adding 'structure container' documents")
        for (c, h) in containers:
            container = dict(base_container)
            container["name"] = c
            container["host"] = h
            container["host_rescaler_ip"] = h
            handler.add_structure(container)
