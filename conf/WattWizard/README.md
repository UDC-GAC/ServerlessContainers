# Timestamp files

This is the default directory to store timestamp files corresponding to different experiments. WattWizard will obtain the metrics from InfluxDB corresponding to these periods to train different power models and serve them through a REST API.

*NOTE: If you want to use other host or container timestamp directories change WattWizard configuration in `src/WattWizard/config.yml`.*



## Files format (.timestamps)
Timestamps files must be stored in the following format:
```shell
<EXP-NAME> <TYPE-OF-EXPERIMENT> (CORES = <CORES>) START: <START-DATE>
<EXP-NAME> <TYPE-OF-EXPERIMENT> (CORES = <CORES>) STOP: <STOP-DATE>
```

With the following meaning:
- `EXP-NAME`: User desired name.
- `TYPE-OF-EXPERIMENT`: The type of experiment run during that period. It can take 2 values: IDLE if it's a period in which the CPU is idle and any other value if it's a period in which train data was obtained.
- `CORES` (Optional): Comma-separated list of cores used in the experiment.
- `START-DATE` or `STOP-DATE`: Timestamp of the beginning or end of the experiment in UTC format `%Y-%m-%d %H:%M:%S%z`.

See the existing timestamp files for a better understanding of the format. The example files are timestamps corresponding to metrics obtained (during stress tests execution) on a node with 2 `Intel Xeon Silver 4216 Cascade Lake-SP` CPUs, each one having 16 physical cores and 32 logical cores (64 cores in total). Each file corresponds to a different core distribution and the `General.timestamps` file contains the timestamps of all the files together.



## Directories

- `./host`: Stores timestamp files corresponding to the collection of metrics on a complete system.
- `./container`: Stores timestamp files corresponding to metrics collection on an isolated container.