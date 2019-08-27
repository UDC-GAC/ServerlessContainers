# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host36 = handler.get_structure("host36")
    host36["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node0": 100, "free": 0},
                "1": {"node0": 100, "free": 0},
                "2": {"node0": 100, "free": 0},
                "3": {},
                "4": {},
                "5": {},
                "6": {"node1": 100, "free": 0},
                "7": {"node1": 100, "free": 0},
                "8": {"node1": 100, "free": 0},
                "9": {},
                "10": {},
                "11": {},
                "12": {"node2": 100, "free": 0},
                "13": {"node2": 100, "free": 0},
                "14": {"node2": 100, "free": 0},
                "15": {},
                "16": {},
                "17": {},
                "18": {"node3": 100, "free": 0},
                "19": {"node3": 100, "free": 0},
                "20": {"node3": 100, "free": 0},
                "21": {},
                "22": {},
                "23": {}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host36)

    host37 = handler.get_structure("host37")
    host37["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node4": 100, "free": 0},
                "1": {"node4": 100, "free": 0},
                "2": {"node4": 100, "free": 0},
                "3": {},
                "4": {},
                "5": {},
                "6": {"node5": 100, "free": 0},
                "7": {"node5": 100, "free": 0},
                "8": {"node5": 100, "free": 0},
                "9": {},
                "10": {},
                "11": {},
                "12": {"node6": 100, "free": 0},
                "13": {"node6": 100, "free": 0},
                "14": {"node6": 100, "free": 0},
                "15": {},
                "16": {},
                "17": {},
                "18": {"node7": 100, "free": 0},
                "19": {"node7": 100, "free": 0},
                "20": {"node7": 100, "free": 0},
                "21": {},
                "22": {},
                "23": {}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host37)

    host38 = handler.get_structure("host38")
    host38["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node8": 100, "free": 0},
                "1": {"node8": 100, "free": 0},
                "2": {"node8": 100, "free": 0},
                "3": {},
                "4": {},
                "5": {},
                "6": {"node9": 100, "free": 0},
                "7": {"node9": 100, "free": 0},
                "8": {"node9": 100, "free": 0},
                "9": {},
                "10": {},
                "11": {},
                "12": {"node10": 100, "free": 0},
                "13": {"node10": 100, "free": 0},
                "14": {"node10": 100, "free": 0},
                "15": {},
                "16": {},
                "17": {},
                "18": {"node11": 100, "free": 0},
                "19": {"node11": 100, "free": 0},
                "20": {"node11": 100, "free": 0},
                "21": {},
                "22": {},
                "23": {}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host38)

    host39 = handler.get_structure("host39")
    host39["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node12": 100, "free": 0},
                "1": {"node12": 100, "free": 0},
                "2": {"node12": 100, "free": 0},
                "3": {},
                "4": {},
                "5": {},
                "6": {"node13": 100, "free": 0},
                "7": {"node13": 100, "free": 0},
                "8": {"node13": 100, "free": 0},
                "9": {},
                "10": {},
                "11": {},
                "12": {"node14": 100, "free": 0},
                "13": {"node14": 100, "free": 0},
                "14": {"node14": 100, "free": 0},
                "15": {},
                "16": {},
                "17": {},
                "18": {"node15": 100, "free": 0},
                "19": {"node15": 100, "free": 0},
                "20": {"node15": 100, "free": 0},
                "21": {},
                "22": {},
                "23": {}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host39)


