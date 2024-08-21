# Timestamp files

This is the default directory to store timestamp files corresponding to different experiments. Files under `./train` directory will be used to train the models. WattWizard will obtain the metrics from InfluxDB corresponding to these periods to train different power models and serve them through a REST API. Files under `./test` will be used to test the models. WattWizard will obtain the metrics corresponding to these periods, predict the estimated power using all models and compare the results with the actual power.

*NOTE: If you want to use other host or container timestamp directories change WattWizard configuration in `src/WattWizard/config.yml`.*



## Files format (.timestamps)
Timestamps files must be stored in the following format:
```shell
<EXP_NAME> <EXP_TYPE> (CORES = <CORES>) START: <START_DATE>
<EXP_NAME> <EXP_TYPE> (CORES = <CORES>) STOP: <STOP_DATE>
```

With the following meaning:
- `EXP_NAME`: User desired name. When we use HW aware models, this name must indicate the specific CPU socket used during the experiment.
- `EXP_TYPE`: The type of experiment run during that period. It can take 2 values: IDLE if it's a period in which the CPU is idle and any other value if it's a period in which train data was obtained.
- `CORES` (Optional): Comma-separated list of cores used in the experiment.
- `START_DATE` or `STOP_DATE`: Timestamp of the beginning or end of the experiment in UTC format `%Y-%m-%d %H:%M:%S%z`.

See the existing timestamp files for a better understanding of the format. The example files are timestamps corresponding to metrics obtained (during stress tests execution) on a node with 2 `Intel Xeon Silver 4216 Cascade Lake-SP` CPUs, each one having 16 physical cores and 32 logical cores (64 cores in total). Each file corresponds to a different core distribution and the `General.timestamps` file contains the timestamps of all the files together.



## Directories in `./train`

- `./default`: Stores timestamp files corresponding to the training of default models.
- `./hw_aware`: Stores timestamp files corresponding to the training of HW aware models.