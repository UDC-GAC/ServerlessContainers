load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "usage")
        |> filter(fn: (r) => r["_field"] == "user" or r["_field"] == "system")
        |> filter(fn: (r) => r["host"] == "stress")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
        |> map(fn: (r) => ({{
            _time: r._time,
            host: r.host,
            _measurement: r._measurement,
            _field: "total_usage",
            _value: (if exists r["user"] then r["user"] else 0.0)
                  + (if exists r["system"] then r["system"] else 0.0)
        }}))
'''

user_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "usage")
        |> filter(fn: (r) => r["_field"] == "user")
        |> filter(fn: (r) => r["host"] == "stress")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

system_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "usage")
        |> filter(fn: (r) => r["_field"] == "system")
        |> filter(fn: (r) => r["host"] == "stress")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

power_query = '''
    from(bucket: "{influxdb_bucket}")
      |> range(start: {start_date}, stop: {stop_date})
      |> filter(fn: (r) => r["_measurement"] == "power")
      |> filter(fn: (r) => r["_field"] == "value")
      |> filter(fn: (r) => r["host"] == "stress")
      |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

container_queries = {
    "load": load_query,
    "user_load": user_load_query,
    "system_load": system_load_query,
    "wait_load": None,
    "freq": None,
    "sumfreq": None,
    "power": power_query,
    "temp": None
}