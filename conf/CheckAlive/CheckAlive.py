# /usr/bin/python
from src.SanityChecker.CheckAliveBase import CheckAliveBase as CheckAlive


def main():
    hosts = ["host0", "host1"]
    REST_SERVICES = [("{0}".format(h), h, "8000") for h in hosts]
    checker = CheckAlive()
    checker.set_REST_services(REST_SERVICES)
    checker.report()


if __name__ == "__main__":
    main()
