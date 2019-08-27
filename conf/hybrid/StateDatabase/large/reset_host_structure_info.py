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
                "3": {"node4": 100, "free": 0},
                "4": {"node4": 100, "free": 0},
                "5": {"node4": 100, "free": 0},
                "6": {"node5": 100, "free": 0},
                "7": {"node5": 100, "free": 0},
                "8": {"node5": 100, "free": 0},
                "9": {"node5": 100, "free": 0},
                "10": {"node5": 100, "free": 0},
                "11": {"node5": 100, "free": 0},
                "12": {"node6": 100, "free": 0},
                "13": {"node6": 100, "free": 0},
                "14": {"node6": 100, "free": 0},
                "15": {"node6": 100, "free": 0},
                "16": {"node6": 100, "free": 0},
                "17": {"node6": 100, "free": 0},
                "18": {"node7": 100, "free": 0},
                "19": {"node7": 100, "free": 0},
                "20": {"node7": 100, "free": 0},
                "21": {"node7": 100, "free": 0},
                "22": {"node7": 100, "free": 0},
                "23": {"node7": 100, "free": 0}
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
                "3": {"node8": 100, "free": 0},
                "4": {"node8": 100, "free": 0},
                "5": {"node8": 100, "free": 0},
                "6": {"node9": 100, "free": 0},
                "7": {"node9": 100, "free": 0},
                "8": {"node9": 100, "free": 0},
                "9": {"node9": 100, "free": 0},
                "10": {"node9": 100, "free": 0},
                "11": {"node9": 100, "free": 0},
                "12": {"node10": 100, "free": 0},
                "13": {"node10": 100, "free": 0},
                "14": {"node10": 100, "free": 0},
                "15": {"node10": 100, "free": 0},
                "16": {"node10": 100, "free": 0},
                "17": {"node10": 100, "free": 0},
                "18": {"node11": 100, "free": 0},
                "19": {"node11": 100, "free": 0},
                "20": {"node11": 100, "free": 0},
                "21": {"node11": 100, "free": 0},
                "22": {"node11": 100, "free": 0},
                "23": {"node11": 100, "free": 0}
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
                "3": {"node12": 100, "free": 0},
                "4": {"node12": 100, "free": 0},
                "5": {"node12": 100, "free": 0},
                "6": {"node13": 100, "free": 0},
                "7": {"node13": 100, "free": 0},
                "8": {"node13": 100, "free": 0},
                "9": {"node13": 100, "free": 0},
                "10": {"node13": 100, "free": 0},
                "11": {"node13": 100, "free": 0},
                "12": {"node14": 100, "free": 0},
                "13": {"node14": 100, "free": 0},
                "14": {"node14": 100, "free": 0},
                "15": {"node14": 100, "free": 0},
                "16": {"node14": 100, "free": 0},
                "17": {"node14": 100, "free": 0},
                "18": {"node15": 100, "free": 0},
                "19": {"node15": 100, "free": 0},
                "20": {"node15": 100, "free": 0},
                "21": {"node15": 100, "free": 0},
                "22": {"node15": 100, "free": 0},
                "23": {"node15": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host39)


