# /usr/bin/python
import StateDatabase.couchDB as couchDB

handler = couchDB.CouchDBServer()

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
          "node2": 100,
          "free": 0
        },
        "3": {
          "node3": 100,
          "free": 0
        },
        "4": {
          "node0": 100,
          "free": 0
        },
        "5": {
          "node1": 100,
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