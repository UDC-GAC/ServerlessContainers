# /usr/bin/python
base_host = dict(
    type='structure',
    subtype='host',
    name="host0",
    host="host0",
    resources=dict(
        cpu=dict(max=2400),
        mem=dict(max=184320)
    )
)


def add_hosts(handler):
    hosts = ["host27", "host28", "host29", "host30", "host31", "host32", "host33", "host34"]

    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print("Adding 'structure hosts' documents")
        for h in hosts:
            host = dict(base_host)
            host["name"] = h
            host["host"] = h
            handler.add_structure(host)
