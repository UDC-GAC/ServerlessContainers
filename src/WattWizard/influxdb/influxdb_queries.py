load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "usage")
        |> filter(fn: (r) => r["_field"] == "user" or r["_field"] == "system")
        |> filter(fn: (r) => r["host"] == \"{host}\")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

user_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "usage")
        |> filter(fn: (r) => r["_field"] == "user")
        |> filter(fn: (r) => r["host"] == \"{host}\")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

system_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "usage")
        |> filter(fn: (r) => r["_field"] == "system")
        |> filter(fn: (r) => r["host"] == \"{host}\")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

power_query = '''
    from(bucket: "{influxdb_bucket}")
      |> range(start: {start_date}, stop: {stop_date})
      |> filter(fn: (r) => r["_measurement"] == "power")
      |> filter(fn: (r) => r["_field"] == "value")
      |> filter(fn: (r) => r["host"] == \"{host}\")
      |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

INFLUXDB_QUERIES = {
    "load": load_query,
    "user_load": user_load_query,
    "system_load": system_load_query,
    "power": power_query,
    "wait_load": None,
    "freq": None,
    "sumfreq": None,
    "temp": None
}