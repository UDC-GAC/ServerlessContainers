# /usr/bin/python
import StateDatabase.couchDB as couchDB

handler = couchDB.CouchDBServer()

containers = ["node0","node1","node2","node3"]
apps = ["app1"]

for c in containers:
    container = handler.get_structure(c)
    limits = handler.get_limits(container)
    limits["resources"]=dict(
                    cpu=dict(upper=170, lower=150, boundary=20),
                    mem=dict(upper=8000, lower=7000, boundary=1000),
                    disk=dict(upper=100, lower=100, boundary=10),
                    net=dict(upper=100, lower=100, boundary=10),
                    energy=dict(upper=15, lower=5, boundary=3)
                )
    handler.update_limit(limits)

app = handler.get_structure("app1")
limits = handler.get_limits(app)
limits["resources"]=dict(
                cpu=dict(upper=300, lower=100, boundary=50),
                mem=dict(upper=14000, lower=2000, boundary=4000),
                disk=dict(upper=100, lower=100, boundary=10),
                net=dict(upper=100, lower=100, boundary=10),
                energy=dict(upper=50, lower=5, boundary=5)
)
handler.update_limit(limits)

dante = handler.get_structure("es-udc-dec-jonatan-dante")
dante["resources"] = {
    "mem": {
      "max": 32768,
      "free": 0
    },
    "cpu": {
      "core_usage_mapping": {
        "0": {
          "node0": 100,
          "free": 0
        },
        "1": {
          "node1": 100,
          "free": 0
        },
        "2": {
          "node0": 100,
          "free": 0
        },
        "3": {
          "node1": 100,
          "free": 0
        },
        "4": {
          "node2": 100,
          "free": 0
        },
        "5": {
          "node3": 100,
          "free": 0
        },
        "6": {
          "node2": 100,
          "free": 0
        },
        "7": {
          "node3": 100,
          "free": 0
        }
      },
      "max": 800,
      "free": 0
    }
  }
handler.update_structure(dante)