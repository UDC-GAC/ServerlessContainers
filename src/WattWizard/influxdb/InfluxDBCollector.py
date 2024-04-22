import warnings
import requests
from influxdb_client import InfluxDBClient
from influxdb_client.client.warnings import MissingPivotFunction
from urllib3.exceptions import ReadTimeoutError

from src.WattWizard.logs.logger import log
from src.WattWizard.influxdb.container_queries import container_queries
from src.WattWizard.influxdb.host_queries import host_queries

INFLUXDB_QUERIES = {"host": host_queries, "container": container_queries}
INFLUXDB_TOKEN = "MyToken"
INFLUXDB_ORG = "MyOrg"

warnings.simplefilter("ignore", MissingPivotFunction)


class InfluxDBCollector:

    influxdb_host = None
    influxdb_url = None
    influxdb_bucket = None

    def __init__(self, host, bucket):
        self.influxdb_host = host
        self.influxdb_url = f"http://{self.influxdb_host}:8086"
        self.influxdb_bucket = bucket
        self.client = InfluxDBClient(url=self.influxdb_url, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)

    def __del__(self):
        self.close_connection()

    def get_influxdb_host(self):
        return self.influxdb_host

    def get_influxdb_bucket(self):
        return self.influxdb_bucket

    def close_connection(self):
        self.client.close()

    def check_influxdb_connection(self):
        try:
            response = requests.get(f"{self.influxdb_url}/health")
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'pass':
                    pass
                else:
                    log(f"Host is reachable but not ready (host = {self.influxdb_host}): {response}", "ERR")
                    exit(1)
            else:
                log(f"Bad host response (host = {self.influxdb_host}): {response}", "ERR")
                exit(1)
        except requests.exceptions.RequestException as e:
            log(f"Failed to connect to InfluxDB (host = {self.influxdb_host}): {e}", "ERR")
            exit(1)

    def check_bucket_exists(self):
        if self.influxdb_bucket is None:
            log(f"No InfluxDB bucket specified", "ERR")
            exit(1)

        if self.client.buckets_api().find_bucket_by_name(self.influxdb_bucket) is None:
            log(f"Unreachable bucket in InfluxDB host {self.influxdb_url}. "
                f"Bucket {self.influxdb_bucket} doesn't exists", "ERR")
            exit(1)

    def get_query(self, var, structure, start_date, stop_date):
        if structure not in INFLUXDB_QUERIES:
            log(f"Querying model variable \'{var}\' for unknown structure \'{structure}\'", "ERR")
            exit(1)
        if var not in INFLUXDB_QUERIES[structure]:
            log(f"Model variable \'{var}\' not supported for structure \'{structure}\'", "ERR")
            exit(1)
        if INFLUXDB_QUERIES[structure][var] is None:
            log(f"Model variable \'{var}\' not yet supported for structure \'{structure}\'", "ERR")
            exit(1)
        return INFLUXDB_QUERIES[structure][var].format(start_date=start_date, stop_date=stop_date,
                                                       influxdb_bucket=self.influxdb_bucket, influxdb_window="2s")

    def query_influxdb(self, var, structure, start_date, stop_date):
        query = self.get_query(var, structure, start_date, stop_date)
        query_api = self.client.query_api()
        result = None
        success = False
        retry = 3
        while not success:
            try:
                result = query_api.query_data_frame(query)
            except ReadTimeoutError:
                if retry != 0:
                    retry -= 1
                    log(f"InfluxDB query has timed out (start_date = {start_date}, "
                        f"stop_date = {stop_date}). Retrying ({retry} tries left)", "WARN")
                else:
                    log(f"InfluxDB query has timed out (start_date = {start_date}, "
                        f"stop_date = {stop_date}). No more tries", "ERR")
                    exit(1)
            except Exception as e:
                log(f"Unexpected error while querying InfluxDB (start_date = {start_date}, stop_date = {stop_date}).", "ERR")
                log(f"{e}", "ERR")
                exit(1)
            else:
                # CHECK EMPTY DATAFRAME!!!
                if result.empty:
                    log(f"There isn't any data between {start_date} and {stop_date}. (var = {var})", "WARN")
                if "_time" in result and result["_time"][0] is not None:
                    return result
                elif retry != 0:
                    retry -= 1
                    log(f"Bad df obtained between {start_date} and {stop_date}. Retrying ({retry} tries left)", "WARN")
                else:
                    log(f"Bad df obtained between {start_date} and {stop_date}. No more tries", "ERR")
                    exit(1)
        return result


class InfluxDBChecker:

    influxdb_host = None
    influxdb_bucket = None
    influxdb_handler = None

    def __init__(self, host, bucket):
        self.influxdb_host = host
        self.influxdb_bucket = bucket

    def __enter__(self):
        self.influxdb_handler = InfluxDBCollector(self.influxdb_host, self.influxdb_bucket)
        return self.influxdb_handler

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.influxdb_handler:
            self.influxdb_handler.close_connection()
        if exc_type is not None:
            log(f"Unexpected error using InfluxDBChecker: exc_type = {exc_type} | exc_val = {exc_val} | exc_tb = {exc_tb}")
        return False
