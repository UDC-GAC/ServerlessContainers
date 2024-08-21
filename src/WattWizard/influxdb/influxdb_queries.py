load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_metrics")
        |> filter(fn: (r) => r["_field"] == "user" or r["_field"] == "system")
        |> filter(fn: (r) => r["core"] == "all")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

user_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_metrics")
        |> filter(fn: (r) => r["_field"] == "user" )
        |> filter(fn: (r) => r["core"] == "all")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

system_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_metrics")
        |> filter(fn: (r) => r["_field"] == "system" )
        |> filter(fn: (r) => r["core"] == "all")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

p_user_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_metrics")
        |> filter(fn: (r) => r["_field"] == "puser" )
        |> filter(fn: (r) => r["core"] == "all")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

p_system_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_metrics")
        |> filter(fn: (r) => r["_field"] == "psystem" )
        |> filter(fn: (r) => r["core"] == "all")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

l_user_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_metrics")
        |> filter(fn: (r) => r["_field"] == "luser" )
        |> filter(fn: (r) => r["core"] == "all")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

l_system_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_metrics")
        |> filter(fn: (r) => r["_field"] == "lsystem" )
        |> filter(fn: (r) => r["core"] == "all")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

user_load_core_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_metrics")
        |> filter(fn: (r) => r["_field"] == "user" )
        |> filter(fn: (r) => r["core"] == \"{core}\")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

system_load_core_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_metrics")
        |> filter(fn: (r) => r["_field"] == "system" )
        |> filter(fn: (r) => r["core"] == \"{core}\")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
'''

power_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "POWER_PACKAGE")
        |> filter(fn: (r) => r["_field"] == "rapl:::PACKAGE_ENERGY:PACKAGE0(W)" or r["_field"] == "rapl:::PACKAGE_ENERGY:PACKAGE1(W)")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> map(fn: (r) => ({{
            _time: r._time,
            host: r.host,
            _measurement: r._measurement,
            _field: "total_power",
            _value: (if exists r["rapl:::PACKAGE_ENERGY:PACKAGE0(W)"] then r["rapl:::PACKAGE_ENERGY:PACKAGE0(W)"] else 0.0)
                  + (if exists r["rapl:::PACKAGE_ENERGY:PACKAGE1(W)"] then r["rapl:::PACKAGE_ENERGY:PACKAGE1(W)"] else 0.0)
        }}))'''

power_pkg0_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "POWER_PACKAGE")
        |> filter(fn: (r) => r["_field"] == "rapl:::PACKAGE_ENERGY:PACKAGE0(W)")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)'''

power_pkg1_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "POWER_PACKAGE")
        |> filter(fn: (r) => r["_field"] == "rapl:::PACKAGE_ENERGY:PACKAGE1(W)")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)'''

INFLUXDB_QUERIES = {
    "load": load_query,
    "user_load": user_load_query,
    "system_load": system_load_query,
    "p_user_load": p_user_load_query,
    "p_system_load": p_system_load_query,
    "l_user_load": l_user_load_query,
    "l_system_load": l_system_load_query,
    "user_load_core": user_load_core_query,
    "system_load_core": system_load_core_query,
    "power": power_query,
    "power_pkg0": power_pkg0_query,
    "power_pkg1": power_pkg1_query,
    "wait_load": None,
    "freq": None,
    "sumfreq": None,
    "temp": None
}