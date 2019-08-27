# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host28 = handler.get_structure("host28")
    host28["resources"] = {
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
    handler.update_structure(host28)

    host29 = handler.get_structure("host29")
    host29["resources"] = {
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
    handler.update_structure(host29)

    host30 = handler.get_structure("host30")
    host30["resources"] = {
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
    handler.update_structure(host30)

    host31 = handler.get_structure("host31")
    host31["resources"] = {
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
    handler.update_structure(host31)

    host32 = handler.get_structure("host32")
    host32["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"kafka4": 100, "free": 0},
                "1": {"kafka4": 100, "free": 0},
                "2": {"kafka4": 100, "free": 0},
                "3": {"kafka4": 100, "free": 0},
                "4": {"kafka4": 100, "free": 0},
                "5": {"kafka4": 100, "free": 0},

                "6": {"hibench2": 100, "free": 0},
                "7": {"hibench2": 100, "free": 0},
                "8": {"hibench2": 100, "free": 0},
                "9": {"hibench2": 100, "free": 0},
                "10": {"hibench2": 100, "free": 0},
                "11": {"hibench2": 100, "free": 0},

                "12": {"hibench3": 100, "free": 0},
                "13": {"hibench3": 100, "free": 0},
                "14": {"hibench3": 100, "free": 0},
                "15": {"hibench3": 100, "free": 0},
                "16": {"hibench3": 100, "free": 0},
                "17": {"hibench3": 100, "free": 0},

                "18": {"slave19": 100, "free": 0},
                "19": {"slave19": 100, "free": 0},
                "20": {"slave19": 100, "free": 0},
                "21": {"slave19": 100, "free": 0},
                "22": {"slave19": 100, "free": 0},
                "23": {"slave19": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host32)

    host33 = handler.get_structure("host33")
    host33["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"kafka5": 100, "free": 0},
                "1": {"kafka5": 100, "free": 0},
                "2": {"kafka5": 100, "free": 0},
                "3": {"kafka5": 100, "free": 0},
                "4": {"kafka5": 100, "free": 0},
                "5": {"kafka5": 100, "free": 0},

                "6": {"slave10": 100, "free": 0},
                "7": {"slave10": 100, "free": 0},
                "8": {"slave10": 100, "free": 0},
                "9": {"slave10": 100, "free": 0},
                "10": {"slave10": 100, "free": 0},
                "11": {"slave10": 100, "free": 0},

                "12": {"slave11": 100, "free": 0},
                "13": {"slave11": 100, "free": 0},
                "14": {"slave11": 100, "free": 0},
                "15": {"slave11": 100, "free": 0},
                "16": {"slave11": 100, "free": 0},
                "17": {"slave11": 100, "free": 0},

                "18": {"slave12": 100, "free": 0},
                "19": {"slave12": 100, "free": 0},
                "20": {"slave12": 100, "free": 0},
                "21": {"slave12": 100, "free": 0},
                "22": {"slave12": 100, "free": 0},
                "23": {"slave12": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host33)

    host34 = handler.get_structure("host34")
    host34["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"kafka6": 100, "free": 0},
                "1": {"kafka6": 100, "free": 0},
                "2": {"kafka6": 100, "free": 0},
                "3": {"kafka6": 100, "free": 0},
                "4": {"kafka6": 100, "free": 0},
                "5": {"kafka6": 100, "free": 0},

                "6": {"slave13": 100, "free": 0},
                "7": {"slave13": 100, "free": 0},
                "8": {"slave13": 100, "free": 0},
                "9": {"slave13": 100, "free": 0},
                "10": {"slave13": 100, "free": 0},
                "11": {"slave13": 100, "free": 0},

                "12": {"slave14": 100, "free": 0},
                "13": {"slave14": 100, "free": 0},
                "14": {"slave14": 100, "free": 0},
                "15": {"slave14": 100, "free": 0},
                "16": {"slave14": 100, "free": 0},
                "17": {"slave14": 100, "free": 0},

                "18": {"slave15": 100, "free": 0},
                "19": {"slave15": 100, "free": 0},
                "20": {"slave15": 100, "free": 0},
                "21": {"slave15": 100, "free": 0},
                "22": {"slave15": 100, "free": 0},
                "23": {"slave15": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host34)

    host35 = handler.get_structure("host35")
    host35["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"kafka7": 100, "free": 0},
                "1": {"kafka7": 100, "free": 0},
                "2": {"kafka7": 100, "free": 0},
                "3": {"kafka7": 100, "free": 0},
                "4": {"kafka7": 100, "free": 0},
                "5": {"kafka7": 100, "free": 0},

                "6": {"slave16": 100, "free": 0},
                "7": {"slave16": 100, "free": 0},
                "8": {"slave16": 100, "free": 0},
                "9": {"slave16": 100, "free": 0},
                "10": {"slave16": 100, "free": 0},
                "11": {"slave16": 100, "free": 0},

                "12": {"slave17": 100, "free": 0},
                "13": {"slave17": 100, "free": 0},
                "14": {"slave17": 100, "free": 0},
                "15": {"slave17": 100, "free": 0},
                "16": {"slave17": 100, "free": 0},
                "17": {"slave17": 100, "free": 0},

                "18": {"slave18": 100, "free": 0},
                "19": {"slave18": 100, "free": 0},
                "20": {"slave18": 100, "free": 0},
                "21": {"slave18": 100, "free": 0},
                "22": {"slave18": 100, "free": 0},
                "23": {"slave18": 100, "free": 0}
            },
            "max": 2400,
            "free": 0
        }
    }
    handler.update_structure(host35)
