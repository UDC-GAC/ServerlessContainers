# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host24 = handler.get_structure("host24")
    host24["resources"] = {
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

                "12": {"slave0": 100, "free": 0},
                "13": {"slave0": 100, "free": 0},
                "14": {"slave0": 100, "free": 0},
                "15": {"slave0": 100, "free": 0},
                "16": {"slave0": 100, "free": 0},
                "17": {"slave0": 100, "free": 0},

                "18": {"slave1": 100, "free": 0},
                "19": {"slave1": 100, "free": 0},
                "20": {"slave1": 100, "free": 0},
                "21": {"slave1": 100, "free": 0},
                "22": {"slave1": 100, "free": 0},
                "23": {"slave1": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host24)

    host25 = handler.get_structure("host25")
    host25["resources"] = {
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

                "6": {"slave2": 100, "free": 0},
                "7": {"slave2": 100, "free": 0},
                "8": {"slave2": 100, "free": 0},
                "9": {"slave2": 100, "free": 0},
                "10": {"slave2": 100, "free": 0},
                "11": {"slave2": 100, "free": 0},

                "12": {"slave3": 100, "free": 0},
                "13": {"slave3": 100, "free": 0},
                "14": {"slave3": 100, "free": 0},
                "15": {"slave3": 100, "free": 0},
                "16": {"slave3": 100, "free": 0},
                "17": {"slave3": 100, "free": 0},

                "18": {"slave4": 100, "free": 0},
                "19": {"slave4": 100, "free": 0},
                "20": {"slave4": 100, "free": 0},
                "21": {"slave4": 100, "free": 0},
                "22": {"slave4": 100, "free": 0},
                "23": {"slave4": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host25)

    host26 = handler.get_structure("host26")
    host26["resources"] = {
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

                "6": {"hibench1": 100, "free": 0},
                "7": {"hibench1": 100, "free": 0},
                "8": {"hibench1": 100, "free": 0},
                "9": {"hibench1": 100, "free": 0},
                "10": {"hibench1": 100, "free": 0},
                "11": {"hibench1": 100, "free": 0},

                "12": {"slave5": 100, "free": 0},
                "13": {"slave5": 100, "free": 0},
                "14": {"slave5": 100, "free": 0},
                "15": {"slave5": 100, "free": 0},
                "16": {"slave5": 100, "free": 0},
                "17": {"slave5": 100, "free": 0},

                "18": {"slave6": 100, "free": 0},
                "19": {"slave6": 100, "free": 0},
                "20": {"slave6": 100, "free": 0},
                "21": {"slave6": 100, "free": 0},
                "22": {"slave6": 100, "free": 0},
                "23": {"slave6": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host26)

    host27 = handler.get_structure("host27")
    host27["resources"] = {
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

                "6": {"slave7": 100, "free": 0},
                "7": {"slave7": 100, "free": 0},
                "8": {"slave7": 100, "free": 0},
                "9": {"slave7": 100, "free": 0},
                "10": {"slave7": 100, "free": 0},
                "11": {"slave7": 100, "free": 0},

                "12": {"slave8": 100, "free": 0},
                "13": {"slave8": 100, "free": 0},
                "14": {"slave8": 100, "free": 0},
                "15": {"slave8": 100, "free": 0},
                "16": {"slave8": 100, "free": 0},
                "17": {"slave8": 100, "free": 0},

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
    handler.update_structure(host27)


