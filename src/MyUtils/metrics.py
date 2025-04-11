# Dictionary containing the mapping between resources and BDWatchdog metrics
RESOURCE_TO_BDW = {
    "container": {
        "cpu": ['proc.cpu.user', 'proc.cpu.kernel'],
        "mem": ['proc.mem.resident', 'proc.mem.virtual'],
        #"disk": ['proc.disk.reads.mb', 'proc.disk.writes.mb'],
        "disk_read": ['proc.disk.reads.mb'],
        "disk_write": ['proc.disk.writes.mb'],
        "energy": ["structure.energy.usage"]
    },
    "application": {
        "cpu": ['structure.cpu.usage'],
        "mem": ['structure.mem.usage'],
        #"disk": ['structure.disk.usage'],
        "disk_read": ['structure.disk_read.usage'],
        "disk_write": ['structure.disk_write.usage'],
        "energy": ['structure.energy.usage']
    }
}

# Dictionaries containing the mapping between resources and ServerlessContainers metrics
RESOURCE_TO_SC = {
    "container": {
        "cpu": ['structure.cpu.usage', 'structure.cpu.user', 'structure.cpu.kernel'],
        "mem": ['structure.mem.usage'],
        #"disk": ['structure.disk.usage'],
        "disk_read": ['structure.disk_read.usage'],
        "disk_write": ['structure.disk_write.usage'],
        "energy": ["structure.energy.usage"]
    },
    "application": {
        "cpu": ['structure.cpu.usage', 'structure.cpu.user', 'structure.cpu.kernel'],
        "mem": ['structure.mem.usage'],
        #"disk": ['structure.disk.usage'],
        "disk_read": ['structure.disk_read.usage'],
        "disk_write": ['structure.disk_write.usage'],
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
        #'structure.disk.usage': ['proc.disk.reads.mb', 'proc.disk.writes.mb'],
        'structure.disk_read.usage': ['proc.disk.reads.mb'],
        'structure.disk_write.usage': ['proc.disk.writes.mb'],
        'structure.energy.usage': ["structure.energy.usage"]
    },
    "application": {
        'structure.cpu.usage': ['structure.cpu.usage'],
        'structure.cpu.user': ['structure.cpu.user'],
        'structure.cpu.kernel': ['structure.cpu.kernel'],
        'structure.mem.usage': ['structure.mem.usage'],
        #'structure.disk.usage': ['structure.disk.usage'],
        'structure.disk_read.usage': ['structure.disk_read.usage'],
        'structure.disk_write.usage': ['structure.disk_write.usage'],
        'structure.energy.usage': ['structure.energy.usage']
    }
}

# Dictionary containing the mapping between structure subtypes and tags
TAGS = {"container": "host", "application": "structure"}