import os
import numpy as np
import pandas as pd
from src.WattWizard.logs.logger import log
from src.WattWizard.model.ModelHandler import ModelHandler

# Train file with the executions of the first core (from 10 to 100 shares). As the first core is common to all the core
# distributions, its samples replace the single-core samples of every model with split points
FIRST_CORE_FILE = "Single_Core"
FOLDS = 5  # Cross-validation folds: the samples of each execution are divided into FOLDS consecutive time blocks
MIN_SAMPLES = 12  # Minimum number of samples on each side of a split point
MIN_GAIN = 0.005  # Minimum MAPE reduction (in percentage points) to add another split point
MAX_SPLIT_POINTS = 6
EXECUTION_GAP = 10  # Seconds between two consecutive samples of different executions


def get_cores(time_series):
    # Number of active cores of the execution of each sample (CORES = <cores> in the timestamps), NaN if unknown. A
    # single core may have been read as a float (e.g., 0.0) from a CSV file
    cores = time_series["cores"].astype(str) if "cores" in time_series else pd.Series("", index=time_series.index)
    return np.where(cores.str.fullmatch(r"\d+(\.0)?|\d+(,\d+)+"), cores.str.count(",") + 1, np.nan)


def get_mape(predictions, y):
    return 100 * float(np.mean(np.abs(predictions - y) / y))


class SplitPointSelector:

    def __init__(self, config, data_loader):
        self.config = config
        self.data_loader = data_loader
        self.model_handler = ModelHandler.get_instance()
        self.timestamps_dir = self.config.get_argument("train_timestamps_dir")
        self.csv_caching = self.config.get_argument("csv_caching_train")
        self.target_error = self.config.get_argument("split_points_target_error")
        self.first_core_data = {}

    @staticmethod
    def has_cores(model, ts_data):
        if np.isnan(get_cores(ts_data)).any():
            log(f"Split points of model {model['name']} need the cores of every execution (CORES = <cores> in its "
                f"timestamps). Skipping split points...", "WARN")
            return False
        return True

    def with_first_core(self, structure, model, ts_data):
        first_core_path = os.path.join(self.timestamps_dir, f"{FIRST_CORE_FILE}.timestamps")
        if model['train_file_name'] == FIRST_CORE_FILE or not os.path.isfile(first_core_path):
            return ts_data

        # Load the executions of the first core only once for each structure
        if structure not in self.first_core_data:
            self.first_core_data[structure] = self.data_loader.load_time_series(
                structure, self.timestamps_dir, FIRST_CORE_FILE, idle=False, csv_caching=self.csv_caching)
        first_core_data = self.first_core_data[structure]
        if first_core_data is None or not self.has_cores(model, first_core_data):
            log(f"Model {model['name']} keeps its own single-core data", "WARN")
            return ts_data

        return pd.concat([first_core_data, ts_data[get_cores(ts_data) > 1]], ignore_index=True)

    @staticmethod
    def _get_folds(ts_data, cores):
        # Fold of each sample: its execution (consecutive samples using the same cores) is divided into FOLDS
        # consecutive time blocks, so that every fold leaves out a block of every execution
        df = pd.DataFrame({"time": pd.to_datetime(ts_data["time"], utc=True), "cores": cores}).sort_values("time")
        new_execution = (df["time"].diff() > pd.Timedelta(seconds=EXECUTION_GAP)) | (df["cores"] != df["cores"].shift())
        execution = new_execution.cumsum()
        rank = df.groupby(execution).cumcount()
        size = df.groupby(execution)["cores"].transform("size")
        return (rank * FOLDS // size).sort_index().to_numpy()

    @staticmethod
    def _fit(instance, model, idle_data, ts_data):
        instance.set_model_vars(model['instance'].get_model_vars())
        instance.set_idle_consumption(idle_data)
        instance.pretrain(time_series=ts_data, data_type="df")
        return instance

    def _cross_validate(self, model, idle_data, ts_data, mask, folds):
        # Predictions of the samples in mask, each one with a model fitted with the samples in mask of the other folds
        predictions = np.full(len(ts_data), np.nan)
        for fold in range(FOLDS):
            test = mask & (folds == fold)
            if test.any():
                instance = self.model_handler.create_model_instance(model['prediction_method'])
                self._fit(instance, model, idle_data, ts_data[mask & (folds != fold)])
                _, predictions[test] = instance.test(time_series=ts_data[test], data_type="df")
        return predictions

    @staticmethod
    def _get_segmented_predictions(full, partial, cores, split_points):
        # Each sample is predicted with the partial-range model of the smallest split point that covers it
        predictions = full.copy()
        for split_point in sorted(split_points, reverse=True):
            covered = cores <= split_point
            predictions[covered] = partial[split_point][covered]
        return predictions

    def _search(self, model, full, partial, cores, y):
        split_points, best = [], get_mape(full, y)
        log(f"Model {model['name']} without split points: MAPE {best:.2f}% ({FOLDS}-fold cross-validation)")
        while best >= self.target_error:
            if len(split_points) == MAX_SPLIT_POINTS:
                log(f"Model {model['name']} reached the limit of {MAX_SPLIT_POINTS} split points")
                break
            trials = [(get_mape(self._get_segmented_predictions(full, partial, cores, split_points + [k]), y), k)
                      for k in partial if k not in split_points]
            if not trials:
                break
            error, split_point = min(trials)
            if error > best - MIN_GAIN:
                log(f"Model {model['name']}: no other split point reduces its MAPE "
                    f"(best: after {split_point} cores, {error:.2f}%)")
                break
            split_points, best = sorted(split_points + [split_point]), error
            log(f"Model {model['name']} with split points after {', '.join(map(str, split_points))} cores: "
                f"MAPE {best:.2f}% ({FOLDS}-fold cross-validation)")
        return split_points

    def split_model(self, structure, model, idle_data, ts_data):
        ts_data = ts_data.reset_index(drop=True)
        cores = get_cores(ts_data)
        y = ts_data["power"].to_numpy()
        folds = self._get_folds(ts_data, cores)

        # Candidate split points: every number of cores leaving enough samples on each side
        candidates = [k for k in range(1, int(cores.max())) if MIN_SAMPLES <= np.sum(cores <= k) <= len(y) - MIN_SAMPLES]
        log(f"Selecting split points for model {model['name']} among {len(candidates)} candidates "
            f"(target MAPE {self.target_error}%)")

        # Cross-validation predictions of the full-range model and of the partial-range model of every candidate
        everything = np.ones(len(y), dtype=bool)
        full = self._cross_validate(model, idle_data, ts_data, everything, folds)
        partial = {k: self._cross_validate(model, idle_data, ts_data, cores <= k, folds) for k in candidates}
        split_points = self._search(model, full, partial, cores, y)
        if not split_points:
            log(f"Model {model['name']} keeps its full range without split points")
            return

        # Train the partial-range model of each split point with all its samples
        for split_point in split_points:
            split_model = self.model_handler.add_split_model(structure, model, split_point)
            self._fit(split_model['instance'], model, idle_data, ts_data[cores <= split_point])

        errors = self._get_segmented_predictions(full, partial, cores, split_points) - y
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        r2 = 1 - float(np.sum(errors ** 2) / np.sum((y - y.mean()) ** 2))
        log(f"Model {model['name']} split after {', '.join(map(str, split_points))} cores with partial-range models "
            f"{', '.join(model['split_points'].values())}: RMSE {rmse:.2f} W, R2 {r2:.3f} ({FOLDS}-fold cross-validation)")
