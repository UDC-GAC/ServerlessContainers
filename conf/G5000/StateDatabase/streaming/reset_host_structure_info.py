# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host7 = handler.get_structure("host7")
    host7["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"kafka0": 100, "free": 0},
                "1": {"kafka0": 100, "free": 0},
                "2": {"kafka0": 100, "free": 0},
                "3": {"kafka0": 100, "free": 0},
                "4": {"kafka0": 100, "free": 0},
                "5": {"kafka0": 100, "free": 0},

                "6": {"hibench0": 100, "free": 0},
                "7": {"hibench0": 100, "free": 0},
                "8": {"hibench0": 100, "free": 0},
                "9": {"hibench0": 100, "free": 0},
                "10": {"hibench0": 100, "free": 0},
                "11": {"hibench0": 100, "free": 0},

                "12": {"hibench1": 100, "free": 0},
                "13": {"hibench1": 100, "free": 0},
                "14": {"hibench1": 100, "free": 0},
                "15": {"hibench1": 100, "free": 0},
                "16": {"hibench1": 100, "free": 0},
                "17": {"hibench1": 100, "free": 0},

                "18": {"slave9": 100, "free": 0},
                "19": {"slave9": 100, "free": 0},
                "20": {"slave9": 100, "free": 0},
                "21": {"slave9": 100, "free": 0},
                "22": {"slave9": 100, "free": 0},
                "23": {"slave9": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host7)

    host8 = handler.get_structure("host8")
    host8["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"kafka1": 100, "free": 0},
                "1": {"kafka1": 100, "free": 0},
                "2": {"kafka1": 100, "free": 0},
                "3": {"kafka1": 100, "free": 0},
                "4": {"kafka1": 100, "free": 0},
                "5": {"kafka1": 100, "free": 0},

                "6": {"slave0": 100, "free": 0},
                "7": {"slave0": 100, "free": 0},
                "8": {"slave0": 100, "free": 0},
                "9": {"slave0": 100, "free": 0},
                "10": {"slave0": 100, "free": 0},
                "11": {"slave0": 100, "free": 0},

                "12": {"slave1": 100, "free": 0},
                "13": {"slave1": 100, "free": 0},
                "14": {"slave1": 100, "free": 0},
                "15": {"slave1": 100, "free": 0},
                "16": {"slave1": 100, "free": 0},
                "17": {"slave1": 100, "free": 0},

                "18": {"slave2": 100, "free": 0},
                "19": {"slave2": 100, "free": 0},
                "20": {"slave2": 100, "free": 0},
                "21": {"slave2": 100, "free": 0},
                "22": {"slave2": 100, "free": 0},
                "23": {"slave2": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host8)

    host9 = handler.get_structure("host9")
    host9["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"kafka2": 100, "free": 0},
                "1": {"kafka2": 100, "free": 0},
                "2": {"kafka2": 100, "free": 0},
                "3": {"kafka2": 100, "free": 0},
                "4": {"kafka2": 100, "free": 0},
                "5": {"kafka2": 100, "free": 0},

                "6": {"slave3": 100, "free": 0},
                "7": {"slave3": 100, "free": 0},
                "8": {"slave3": 100, "free": 0},
                "9": {"slave3": 100, "free": 0},
                "10": {"slave3": 100, "free": 0},
                "11": {"slave3": 100, "free": 0},

                "12": {"slave4": 100, "free": 0},
                "13": {"slave4": 100, "free": 0},
                "14": {"slave4": 100, "free": 0},
                "15": {"slave4": 100, "free": 0},
                "16": {"slave4": 100, "free": 0},
                "17": {"slave4": 100, "free": 0},

                "18": {"slave5": 100, "free": 0},
                "19": {"slave5": 100, "free": 0},
                "20": {"slave5": 100, "free": 0},
                "21": {"slave5": 100, "free": 0},
                "22": {"slave5": 100, "free": 0},
                "23": {"slave5": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host9)

    host10 = handler.get_structure("host10")
    host10["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"kafka3": 100, "free": 0},
                "1": {"kafka3": 100, "free": 0},
                "2": {"kafka3": 100, "free": 0},
                "3": {"kafka3": 100, "free": 0},
                "4": {"kafka3": 100, "free": 0},
                "5": {"kafka3": 100, "free": 0},

                "6": {"slave6": 100, "free": 0},
                "7": {"slave6": 100, "free": 0},
                "8": {"slave6": 100, "free": 0},
                "9": {"slave6": 100, "free": 0},
                "10": {"slave6": 100, "free": 0},
                "11": {"slave6": 100, "free": 0},

                "12": {"slave7": 100, "free": 0},
                "13": {"slave7": 100, "free": 0},
                "14": {"slave7": 100, "free": 0},
                "15": {"slave7": 100, "free": 0},
                "16": {"slave7": 100, "free": 0},
                "17": {"slave7": 100, "free": 0},

                "18": {"slave8": 100, "free": 0},
                "19": {"slave8": 100, "free": 0},
                "20": {"slave8": 100, "free": 0},
                "21": {"slave8": 100, "free": 0},
                "22": {"slave8": 100, "free": 0},
                "23": {"slave8": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host10)


