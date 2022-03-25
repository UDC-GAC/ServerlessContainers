# /usr/bin/python
import json
import sys

CONTAINERS_LIST = ["node0", "node1"]

def get_metric(metric, tags):
    return {
          "metric": metric,
          "aggregator": "zimsum",
          "tags": [tags]
    }

def get_node_cpu(node):
    cont = dict()
    cont["metrics"] = list()
    cont["metrics"].append(get_metric("proc.cpu.user", "host={0}".format(node)))
    cont["metrics"].append(get_metric("proc.cpu.kernel", "host={0}".format(node)))
    cont["metrics"].append(get_metric("structure.cpu.max", "structure={0}".format(node)))
    cont["metrics"].append(get_metric("limit.cpu.upper", "structure={0}".format(node)))
    cont["metrics"].append(get_metric("structure.cpu.current", "structure={0}".format(node)))
    cont["metrics"].append(get_metric("limit.cpu.lower", "structure={0}".format(node)))
    cont["metrics"].append(get_metric("structure.cpu.min", "structure={0}".format(node)))
    cont["yranges"] = dict({"ymin": 0, "ymax": 250})
    return cont

def generate_cpu():
    all = dict()
    all["timeseries"] = list()

    for node in ["node0", "node1"]:
        all["timeseries"].append(get_node_cpu(node))

    return json.dumps(all, indent=2, sort_keys=True)

def get_node_mem(node):
    cont = dict()
    cont["metrics"] = list()
    cont["metrics"].append(get_metric("proc.mem.resident", "host={0}".format(node)))
    cont["metrics"].append(get_metric("structure.mem.max", "structure={0}".format(node)))
    cont["metrics"].append(get_metric("limit.mem.upper", "structure={0}".format(node)))
    cont["metrics"].append(get_metric("structure.mem.current", "structure={0}".format(node)))
    cont["metrics"].append(get_metric("limit.mem.lower", "structure={0}".format(node)))
    cont["metrics"].append(get_metric("structure.mem.min", "structure={0}".format(node)))
    cont["yranges"] = dict({"ymin": 0, "ymax": 3000})
    return cont

def generate_mem():
    all = dict()
    all["timeseries"] = list()

    for node in CONTAINERS_LIST:
        all["timeseries"].append(get_node_cpu(node))

    return json.dumps(all, indent=2, sort_keys=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Input arguments are 'cpu' and 'mem'")
    else:
        for arg in sys.argv:
            if arg == "cpu":
                f = open("cpu.json", "w")
                f.write(generate_cpu())
                f.close()
            elif arg == "mem":
                f = open("mem.json", "w")
                f.write(generate_mem())
                f.close()




