# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host0 = handler.get_structure("host0")
    host0["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node0": 100, "free": 0},
                "1": {"node0": 100, "free": 0},
                "2": {"node0": 100, "free": 0},
                "3": {"node0": 100, "free": 0},
                "4": {"node0": 100, "free": 0},
                "5": {"node0": 100, "free": 0},
                "6": {"node1": 100, "free": 0},
                "7": {"node1": 100, "free": 0},
                "8": {"node1": 100, "free": 0},
                "9": {"node1": 100, "free": 0},
                "10": {"node1": 100, "free": 0},
                "11": {"node1": 100, "free": 0},
                "12": {"node2": 100, "free": 0},
                "13": {"node2": 100, "free": 0},
                "14": {"node2": 100, "free": 0},
                "15": {"node2": 100, "free": 0},
                "16": {"node2": 100, "free": 0},
                "17": {"node2": 100, "free": 0},
                "18": {"node3": 100, "free": 0},
                "19": {"node3": 100, "free": 0},
                "20": {"node3": 100, "free": 0},
                "21": {"node3": 100, "free": 0},
                "22": {"node3": 100, "free": 0},
                "23": {"node3": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host0)


