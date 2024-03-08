import datetime
from termcolor import colored


def print_header():
    print("REAL TIME WATT WIZARD")
    print("Real Time CPU Power Consumption Modeling")


def log(message, message_type="INFO", print_log=True):
    timestamp = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    header_colors = {
        "INFO": ("white", "on_green"),
        "WARN": ("white", "on_yellow"),
        "ERR": ("white", "on_red"),
    }
    color, on_color = header_colors.get(message_type)
    header = colored(f"[{timestamp} {message_type}]", color, on_color)
    log_entry = f"[{timestamp} {message_type}] {message}\n"

    if print_log:
        print(f"{header} {message}")
