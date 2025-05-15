# Dictionary containing the mapping between resources and BDWatchdog metrics
RESOURCE_TO_BDW = {
    "container": {
        "cpu": ['proc.cpu.user', 'proc.cpu.kernel'],
        "mem": ['proc.mem.resident', 'proc.mem.virtual'],
        "disk": ['proc.disk.reads.mb', 'proc.disk.writes.mb'],
        "net": ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb'],
        "energy": ['structure.energy.usage']
    },
    "application": {
        "cpu": ['structure.cpu.usage'],
        "mem": ['structure.mem.usage'],
        "disk": ['structure.disk.usage'],
        "net": ['structure.net.usage'],
        "energy": ['structure.energy.usage']
    }
}

# Dictionaries containing the mapping between resources and ServerlessContainers metrics
RESOURCE_TO_SC = {
    "container": {
        "cpu": ['structure.cpu.usage', 'structure.cpu.user', 'structure.cpu.kernel'],
        "mem": ['structure.mem.usage'],
        "disk": ['structure.disk.usage'],
        "net": ['structure.net.usage'],
        "energy": ["structure.energy.usage"]
    },
    "application": {
        "cpu": ['structure.cpu.usage', 'structure.cpu.user', 'structure.cpu.kernel'],
        "mem": ['structure.mem.usage'],
        "disk": ['structure.disk.usage'],
        "net": ['structure.net.usage'],
        "energy": ['structure.energy.usage']
    }
}

# Dictionary containing the mapping between ServerlessContainers metrics and BDWatchdog metrics
SC_TO_BDW = {
    "container": {
        'structure.cpu.usage': ['proc.cpu.user', 'proc.cpu.kernel'],
        'structure.cpu.user': ['proc.cpu.user'],
        'structure.cpu.kernel': ['proc.cpu.kernel'],
        'structure.mem.usage': ['proc.mem.resident'],
        'structure.disk.usage': ['proc.disk.reads.mb', 'proc.disk.writes.mb'],
        "structure.net.usage": ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb'],
        'structure.energy.usage': ["structure.energy.usage"]
    },
    "application": {
        'structure.cpu.usage': ['structure.cpu.usage'],
        'structure.cpu.user': ['structure.cpu.user'],
        'structure.cpu.kernel': ['structure.cpu.kernel'],
        'structure.mem.usage': ['structure.mem.usage'],
        'structure.disk.usage': ['structure.disk.usage'],
        "structure.net.usage": ['structure.net.usage'],
        'structure.energy.usage': ['structure.energy.usage']
    }
}

# Dictionary containing the mapping between structure subtypes and tags
TAGS = {"container": "host", "application": "structure"}

# Dictionary containing the mapping between resource names and ServerlessContainers metrics
TRANSLATOR_DICT = {
    "cpu": "structure.cpu.usage",
    "user": "structure.cpu.user",
    "kernel": "structure.cpu.kernel",
    "mem": "structure.mem.usage",
    "disk": "structure.disk.usage",
    "net": "structure.net.usage",
    "energy": "structure.energy.usage"
}
