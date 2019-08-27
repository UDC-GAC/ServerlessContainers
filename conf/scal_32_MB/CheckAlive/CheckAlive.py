# /usr/bin/python
from src.MyUtils.CheckAliveBase import CheckAliveBase as CheckAlive


def main():
    infrastructure = "scal"
    hosts = ["host16", "host17", "host18", "host19", "host20", "host21", "host22", "host23"]
    REST_SERVICES = [("{0}-rescaler".format(h), h, "8000") for h in hosts]
    checker = CheckAlive()
    checker.set_infrastructure_name(infrastructure)
    checker.set_REST_services(REST_SERVICES)
    checker.report()


if __name__ == "__main__":
    main()
