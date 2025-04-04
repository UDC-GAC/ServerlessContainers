from src.WattWizard.logs.logger import log


def is_hw_aware_compatible(file):
    try:
        with open(file, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        log(f"Error while parsing timestamps (file doesn't exists): {file}", "ERR")
        return False
    for line in lines:
        parts = line.split(" ")
        if len(parts) < 2:
            continue
        exp_name, exp_type = parts[0], parts[1]
        if exp_name.startswith("CPU"):
            return True
        elif exp_type != "IDLE":
            return False
    return False
