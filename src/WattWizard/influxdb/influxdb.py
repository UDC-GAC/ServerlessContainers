import warnings
from influxdb_client import InfluxDBClient
from influxdb_client.client.warnings import MissingPivotFunction
from urllib3.exceptions import ReadTimeoutError

from src.WattWizard.influxdb.influxdb_env import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG
from src.WattWizard.logs.logger import log

warnings.simplefilter("ignore", MissingPivotFunction)


def check_bucket_exists(bucket_name):
    if bucket_name is None:
        log(f"No InfluxDB bucket specified. You must specify a bucket to " +
        "retrieve data from when using a train timestamps file.", "ERR")
        exit(1)
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    buckets_api = client.buckets_api()
    if buckets_api.find_bucket_by_name(bucket_name) is None:
        log(f"Specified bucket {bucket_name} doesn't exists", "ERR")
        exit(1)


def query_influxdb(query, start_date, stop_date, bucket):
    retry = 3
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    query_api = client.query_api()
    query = query.format(start_date=start_date, stop_date=stop_date, influxdb_bucket=bucket, influxdb_window="2s")
    while retry != 0:
        try:
            result = query_api.query_data_frame(query)
        except ReadTimeoutError:
            if retry != 0:
                retry -= 1
                log(f"InfluxDB query has timed out (start_date = {start_date}, stop_date = {stop_date}). Retrying ({retry} tries left)", "WARN")
            else:
                log(f"InfluxDB query has timed out (start_date = {start_date}, stop_date = {stop_date}). No more tries", "ERR")
        except Exception as e:
            log(f"Unexpected error while querying InfluxDB (start_date = {start_date}, stop_date = {stop_date}).", "ERR")
            log(f"{e}", "ERR")
            exit(1)
        else:
            if result["_time"][0] is not None:
                retry = 0
            elif retry != 0:
                retry -= 1
                log(f"Bad df obtained between {start_date} and {stop_date}. Retrying ({retry} tries left)", "WARN")
            else:
                log(f"Bad df obtained between {start_date} and {stop_date}. No more tries", "ERROR")
                exit(1)
    return result
