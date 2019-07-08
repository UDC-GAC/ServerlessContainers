# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host4 = handler.get_structure("host4")
    host4["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"aux0": 100, "free": 0},
                "1": {"aux0": 100, "free": 0},
                "2": {"aux0": 100, "free": 0},
                "3": {"aux0": 100, "free": 0},
                "4": {"aux0": 100, "free": 0},
                "5": {"aux0": 100, "free": 0},
                "6": {"aux0": 100, "free": 0},

                "7": {"pre0": 100, "free": 0},
                "8": {"pre0": 100, "free": 0},
                "9": {"pre0": 100, "free": 0},
                "10": {"pre0": 100, "free": 0},
                "11": {"pre0": 100, "free": 0},
                "12": {"pre0": 100, "free": 0},
                "13": {"pre0": 100, "free": 0},

                "14": {"pre1": 100, "free": 0},
                "15": {"pre1": 100, "free": 0},
                "16": {"pre1": 100, "free": 0},
                "17": {"pre1": 100, "free": 0},
                "18": {"pre1": 100, "free": 0},
                "19": {"pre1": 100, "free": 0},
                "20": {"pre1": 100, "free": 0},
            },
            "max": 3600,
            "free": 0
        }
    }
    handler.update_structure(host4)

    host5 = handler.get_structure("host5")
    host5["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"comp0": 100, "free": 0},
                "1": {"comp0": 100, "free": 0},
                "2": {"comp0": 100, "free": 0},
                "3": {"comp0": 100, "free": 0},
                "4": {"comp0": 100, "free": 0},
                "5": {"comp0": 100, "free": 0},
                "6": {"comp0": 100, "free": 0},

                "7": {"comp1": 100, "free": 0},
                "8": {"comp1": 100, "free": 0},
                "9": {"comp1": 100, "free": 0},
                "10": {"comp1": 100, "free": 0},
                "11": {"comp1": 100, "free": 0},
                "12": {"comp1": 100, "free": 0},
                "13": {"comp1": 100, "free": 0},

                "14": {"comp2": 100, "free": 0},
                "15": {"comp2": 100, "free": 0},
                "16": {"comp2": 100, "free": 0},
                "17": {"comp2": 100, "free": 0},
                "18": {"comp2": 100, "free": 0},
                "19": {"comp2": 100, "free": 0},
                "20": {"comp2": 100, "free": 0},

                "21": {"pre2": 100, "free": 0},
                "22": {"pre2": 100, "free": 0},
                "23": {"pre2": 100, "free": 0},
                "24": {"pre2": 100, "free": 0},
                "25": {"pre2": 100, "free": 0},
                "26": {"pre2": 100, "free": 0},
                "27": {"pre2": 100, "free": 0}
            },
            "max": 2800,
            "free": 0
        }
    }
    handler.update_structure(host5)

    host6 = handler.get_structure("host6")
    host6["resources"] = {
        "mem": {
            "max": 737280,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"pre3": 100, "free": 0},
                "1": {"pre3": 100, "free": 0},
                "2": {"pre3": 100, "free": 0},
                "3": {"pre3": 100, "free": 0},
                "4": {"pre3": 100, "free": 0},
                "5": {"pre3": 100, "free": 0},
                "6": {"pre3": 100, "free": 0},

                "7": {"comp3": 100, "free": 0},
                "8": {"comp3": 100, "free": 0},
                "9": {"comp3": 100, "free": 0},
                "10": {"comp3": 100, "free": 0},
                "11": {"comp3": 100, "free": 0},
                "12": {"comp3": 100, "free": 0},
                "13": {"comp3": 100, "free": 0},

                "14": {"comp4": 100, "free": 0},
                "15": {"comp4": 100, "free": 0},
                "16": {"comp4": 100, "free": 0},
                "17": {"comp4": 100, "free": 0},
                "18": {"comp4": 100, "free": 0},
                "19": {"comp4": 100, "free": 0},
                "20": {"comp4": 100, "free": 0},

                "21": {"comp5": 100, "free": 0},
                "22": {"comp5": 100, "free": 0},
                "23": {"comp5": 100, "free": 0},
                "24": {"comp5": 100, "free": 0},
                "25": {"comp5": 100, "free": 0},
                "26": {"comp5": 100, "free": 0},
                "27": {"comp5": 100, "free": 0}
            },
            "max": 2800,
            "free": 0
        }
    }
    handler.update_structure(host6)



