load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "percpu")
        |> filter(fn: (r) => r["_field"] == "user" or r["_field"] == "system")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
        |> timeShift(duration: -6s)
        |> group(columns: ["_measurement"])
        |> aggregateWindow(every: {influxdb_window}, fn: sum, createEmpty: false)'''

user_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "percpu")
        |> filter(fn: (r) => r["_field"] == "user" )
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
        |> timeShift(duration: -6s)
        |> group(columns: ["_measurement"])
        |> aggregateWindow(every: {influxdb_window}, fn: sum, createEmpty: false)'''

system_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "percpu")
        |> filter(fn: (r) => r["_field"] == "system" )
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
        |> timeShift(duration: -6s)
        |> group(columns: ["_measurement"])
        |> aggregateWindow(every: {influxdb_window}, fn: sum, createEmpty: false)'''

wait_load_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "percpu")
        |> filter(fn: (r) => r["_field"] == "iowait" )
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
        |> timeShift(duration: -6s)
        |> group(columns: ["_measurement"])
        |> aggregateWindow(every: {influxdb_window}, fn: sum, createEmpty: false)'''

freq_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_frequency")
        |> filter(fn: (r) => r["_field"] == "average" )
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)'''

sumfreq_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "cpu_frequency")
        |> filter(fn: (r) => r["_field"] == "sum" )
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
        |> map(fn: (r) => ({{
            _time: r._time,
            _value: r._value / 1000.0
        }}))'''

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

temp_query = '''
    from(bucket: "{influxdb_bucket}")
        |> range(start: {start_date}, stop: {stop_date})
        |> filter(fn: (r) => r["_measurement"] == "sensors")
        |> filter(fn: (r) => r["_field"] == "value")
        |> filter(fn: (r) => r["label"] == "Package id 0" or r["label"] == "Package id 1")
        |> aggregateWindow(every: {influxdb_window}, fn: mean, createEmpty: false)
        |> pivot(rowKey:["_time"], columnKey: ["label"], valueColumn: "_value")
        |> map(fn: (r) => ({{
            _time: r._time,
            _value: (if exists r["Package id 0"] then r["Package id 0"] else 0.0) 
                  + (if exists r["Package id 1"] then r["Package id 1"] else 0.0)
        }}))
'''

var_query = {
    "load": load_query,
    "user_load": user_load_query,
    "system_load": system_load_query,
    "wait_load": wait_load_query,
    "freq": freq_query,
    "sumfreq": sumfreq_query,
    "power": power_query,
    "temp": temp_query
}