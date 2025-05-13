# Timestamp files

This is the default directory to store timestamp files corresponding to different experiments. Files under `./train` directory will be used to train the models. Accordingly, WattWizard will obtain the metrics from InfluxDB corresponding to these periods to train different power models and serve them through a REST API. Then, files under `./test` will be used to test the models, so WattWizard will also obtain the metrics corresponding to these periods, predict the estimated power using all models and compare the results with the actual power.

*NOTE: If you want to use other timestamp directories change WattWizard configuration in `src/WattWizard/config.yml`.*



## Timestamp files inner format
Timestamp files must follow the format below:
```shell
<EXP_NAME> <EXP_TYPE> (CORES = <CORES>) START: <START_DATE>
<EXP_NAME> <EXP_TYPE> (CORES = <CORES>) STOP: <STOP_DATE>
```

With the following meaning:
- `EXP_NAME`: User desired name. When we use HW aware models, this name must indicate the specific CPU socket used during the experiment.
- `EXP_TYPE`: The type of experiment run during that period. It can take 2 values: IDLE if it's a period in which the CPU is idle and any other value if it's a period in which train data was obtained.
- `CORES` (Optional): Comma-separated list of cores used in the experiment.
- `START_DATE` or `STOP_DATE`: Timestamp of the beginning or end of the experiment in UTC format `%Y-%m-%d %H:%M:%S%z`.

See the existing timestamp files for a better understanding of the format. The example files are timestamps corresponding to metrics collected on a server with 2 `Intel Xeon Silver 4216 Cascade Lake-SP` CPUs, each one having 16 physical cores and 32 logical cores (64 cores in total). Each file may correspond to different workloads, core distributions and stress patterns.



## Training timestamp files
Directory `./train` is composed of different subdirectories corresponding to specific use cases:
- `./arx`: Stores timestamp files more suitable for ARX model training.
- `./default`: Stores timestamp files suitable for almost any model.
- `./hw_aware`: Stores timestamp files adapted for HW aware model training.

### Naming conventions

The training timestamps correspond to periods in which stress tests have been executed and these files have been named according to the workloads they include. They can include:
- `USR`: 'all' stress-ng workload
- `SYS`: 'sysinfo' stress-ng workload
- `IO`: 'iomix' stress-ng workload

These tests can also be run following different patterns to cover all possible CPU usage values. Possible patterns are:
- `UP`: Gradually increase CPU usage from 0 to maximum.
- `DW`: Gradually decrease CPU usage from maximum to 0.
- `ZZ`: Follow a 'zigzag' pattern going from high to low CPU usage values and vice versa.
- `UN`: Use random CPU usage value following an uniform distribution from 0 to maximum.

Additionally, each workload have been run using different core distributions. The core distribution define the set of cores used to take new cores or remove them when increasing or decreasing CPU usage on each pattern. Supported core distributions are:
- `1C`: Stress a single core (patterns will range from 0 to one core).
- `GP`: Only physical cores, one CPU at a time.
- `SP`: Only physical cores, alternating between CPUs.
- `GPANDL`: Pairs of physical and logical cores, one CPU at a time.
- `G1P2L`: Physical cores first, then logical cores, one CPU at a time.
- `GPPLL`: Physical cores first, one CPU at a time, then logical cores.
- `SPANDL`: Pairs of physical and logical cores, alternating between CPUs.
- `SPPLL`: Physical cores first, alternating between CPUs, then logical cores.

Therefore, naming convention is `<WORKLOADS>_<PATTERN>_<CORE_DISTRIBUTION>`. Some examples can be seen in the table below:

| Filename (.timestamps) | Workloads (stress-ng) | Pattern | Core Distribution         |
| ---------------------- | --------------------- | ------- | ------------------------- |
| `USR_SYS_UP`           | `all`, `sysinfo`      | `UP`    | all core distributions    |
| `USR_SYS_UP_GP12L`     | `all`, `sysinfo`      | `UP`    | `GP12L`                   |
| `USR_SYS_UP_1C`        | `all`, `sysinfo`      | `UP`    | `1C` (single core stress) |
| `IO_UP`                | `iomix`               | `UP`    | all core distributions    |
| `USR_IO_UP`            | `all`, `iomix`        | `UP`    | all core distributions    |
| `USR_SYS_ZZ_SPANDL`    | `all`, `sysinfo`      | `ZZ`    | `SPANDL`                  |
| `USR_SYS_UN`           | `all`, `sysinfo`      | `UN`    | all core distributions    |



## Test timestamp files

Directory `./test` store timestamp files corresponding to periods where test workloads have been executed.

### Naming conventions

These files follow the same naming conventions as the training files, adding new workloads, as they typically include standardised workloads (e.g. NPB benchmark tests). Some examples can be seen in the table below:

| Filename (.timestamps) | Workloads                    | Pattern | Core Distribution         |
| ---------------------- | ---------------------------- | ------- | ------------------------- |
| `BT_UP_GPPLL`          | `BT` (NPB)                   | `UP`    | `GPPLL`                   |
| `IS_UP_1C`             | `IS` (NPB)                   | `UP`    | `1C` (single core stress) |
| `USR_SYS_UP_ZZ_G1P2L`  | `all`, `sysinfo` (stress-ng) | `ZZ`    | `G1P2L`                   |
