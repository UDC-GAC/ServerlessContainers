# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host16 = handler.get_structure("host16")
    host16["resources"] = {
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
            "free": 1200
        }
    }
    handler.update_structure(host16)

    host17 = handler.get_structure("host17")
    host17["resources"] = {
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
            "free": 1200
        }
    }
    handler.update_structure(host17)

    host18 = handler.get_structure("host18")
    host18["resources"] = {
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
            "free": 1200
        }
    }
    handler.update_structure(host18)

    host19 = handler.get_structure("host19")
    host19["resources"] = {
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
            "free": 1200
        }
    }
    handler.update_structure(host19)

    host20 = handler.get_structure("host20")
    host20["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node16": 100, "free": 0},
                "1": {"node16": 100, "free": 0},
                "2": {"node16": 100, "free": 0},
                "3": {},
                "4": {},
                "5": {},
                "6": {"node17": 100, "free": 0},
                "7": {"node17": 100, "free": 0},
                "8": {"node17": 100, "free": 0},
                "9": {},
                "10": {},
                "11": {},
                "12": {"node18": 100, "free": 0},
                "13": {"node18": 100, "free": 0},
                "14": {"node18": 100, "free": 0},
                "15": {},
                "16": {},
                "17": {},
                "18": {"node19": 100, "free": 0},
                "19": {"node19": 100, "free": 0},
                "20": {"node19": 100, "free": 0},
                "21": {},
                "22": {},
                "23": {}
            },
            "max": 2400,
            "free": 1200
        }
    }
    handler.update_structure(host20)

    host21 = handler.get_structure("host21")
    host21["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node20": 100, "free": 0},
                "1": {"node20": 100, "free": 0},
                "2": {"node20": 100, "free": 0},
                "3": {},
                "4": {},
                "5": {},
                "6": {"node21": 100, "free": 0},
                "7": {"node21": 100, "free": 0},
                "8": {"node21": 100, "free": 0},
                "9": {},
                "10": {},
                "11": {},
                "12": {"node22": 100, "free": 0},
                "13": {"node22": 100, "free": 0},
                "14": {"node22": 100, "free": 0},
                "15": {},
                "16": {},
                "17": {},
                "18": {"node23": 100, "free": 0},
                "19": {"node23": 100, "free": 0},
                "20": {"node23": 100, "free": 0},
                "21": {},
                "22": {},
                "23": {}
            },
            "max": 2400,
            "free": 1200
        }
    }
    handler.update_structure(host21)

    host22 = handler.get_structure("host22")
    host22["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node24": 100, "free": 0},
                "1": {"node24": 100, "free": 0},
                "2": {"node24": 100, "free": 0},
                "3": {},
                "4": {},
                "5": {},
                "6": {"node25": 100, "free": 0},
                "7": {"node25": 100, "free": 0},
                "8": {"node25": 100, "free": 0},
                "9": {},
                "10": {},
                "11": {},
                "12": {"node26": 100, "free": 0},
                "13": {"node26": 100, "free": 0},
                "14": {"node26": 100, "free": 0},
                "15": {},
                "16": {},
                "17": {},
                "18": {"node27": 100, "free": 0},
                "19": {"node27": 100, "free": 0},
                "20": {"node27": 100, "free": 0},
                "21": {},
                "22": {},
                "23": {}
            },
            "max": 2400,
            "free": 1200
        }
    }
    handler.update_structure(host22)

    host23 = handler.get_structure("host23")
    host23["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node28": 100, "free": 0},
                "1": {"node28": 100, "free": 0},
                "2": {"node28": 100, "free": 0},
                "3": {},
                "4": {},
                "5": {},
                "6": {"node29": 100, "free": 0},
                "7": {"node29": 100, "free": 0},
                "8": {"node29": 100, "free": 0},
                "9": {},
                "10": {},
                "11": {},
                "12": {"node30": 100, "free": 0},
                "13": {"node30": 100, "free": 0},
                "14": {"node30": 100, "free": 0},
                "15": {},
                "16": {},
                "17": {},
                "18": {"node31": 100, "free": 0},
                "19": {"node31": 100, "free": 0},
                "20": {"node31": 100, "free": 0},
                "21": {},
                "22": {},
                "23": {}
            },
            "max": 2400,
            "free": 1200
        }
    }
    handler.update_structure(host23)


