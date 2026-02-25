import time
import logging
from logging.handlers import RotatingFileHandler

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb


class Service:
    """Base class for all services."""

    MAX_LOG_SIZE = 100 * 1024 * 1024  # 100 MB
    BACKUP_COUNT = 1  # Number of backup log files to keep

    def __init__(self, service_name, config_validator, default_config, sleep_attr="polling_frequency"):
        self.service_name = service_name
        self.config_validator = config_validator
        self._default_config = default_config
        self._sleep_attr = sleep_attr  # e.g. "polling_frequency" or "window_timelapse"
        self.couchdb_handler = couchdb.CouchDBServer()
        self.active, self.debug = None, None

    def log_info(self, msg):
        utils.log_info(msg, self.debug)

    def log_warning(self, msg):
        utils.log_warning(msg, self.debug)

    def log_error(self, msg):
        utils.log_error(msg, self.debug)

    # --------- Functions to be overwritten by specific services ---------

    def on_start(self):
        """Things to do only once before loop starts."""
        pass

    def on_config_updated(self, service_config):
        """Things to fo after configuration have been updated (config have been dumped in class attributes)."""
        pass

    def invalid_conf(self, service_config):
        """Check if current configuration is invalid. Must return a tuple (bool, str) where bool indicates
        if config is invalid and str is a message explaining why. By default, the config validator is used."""
        return self.config_validator.invalid_conf(service_config)

    def work(self):
        """
        Specific loop work to be done. This function can be synchronous or asynchronous. It must return:
          - None if work is synchronous
          - Thread if work is asynchronous
        """
        raise NotImplementedError

    def compute_sleep_time(self):
        """Compute the time to sleep between iterations. By default, it just returns the value of the attribute
        indicated by self._sleep_attr."""
        val = getattr(self, self._sleep_attr, None)
        if val is None:
            raise AttributeError(f"Sleep attribute '{self._sleep_attr}' not found on {self}")
        return val

    # --------- Auxiliar functions ---------

    def _update_config(self, service_config):
        # Get service info
        service = utils.get_service(self.couchdb_handler, self.service_name)

        # Heartbeat
        utils.beat(self.couchdb_handler, self.service_name)

        # Update service configuration
        service_config.set_config(service["config"])

        # Update service instance attributes according to new configuration
        for k, v in service_config.get_config().items():
            setattr(self, k.lower(), v)

    def _print_config(self, service_config):
        utils.log_info("Config is as follows:", self.debug)
        utils.log_info(".............................................", self.debug)

        for key in service_config.get_config().keys():
            value = getattr(self, key.lower(), None)
            utils.log_info(f"{key.replace('_', ' ').capitalize()} -> {value}", self.debug)

        utils.log_info(".............................................", self.debug)

    def _start_epoch(self):
        utils.log_info("----------------------", self.debug)
        utils.log_info("Starting Epoch", self.debug)
        return time.time()

    def _end_epoch(self, window_difference, t0):
        t1 = time.time()
        time_proc = "%.2f" % (t1 - t0 - window_difference)
        time_total = "%.2f" % (t1 - t0)
        window_difference_str = "%.2f" % window_difference
        utils.log_info("Epoch processed in {0} seconds ({1} processing and {2} sleeping)".format(time_total, time_proc, window_difference_str), self.debug)
        utils.log_info("----------------------\n", self.debug)

    def _wait_operation_thread(self, thread):
        """This is used in services like the snapshoters or the Guardian that use threads to carry out operations.
        A main thread is launched that spawns the needed threads to carry out the operations. The service waits for this
        thread to finish.
        Args:
            thread (Python Thread): The thread that has spawned the basic threads that carry out operations as needed
        """
        if thread and thread.is_alive():
            utils.log_warning("Previous thread didn't finish and next poll should start now", self.debug)
            utils.log_warning("Going to wait until thread finishes before proceeding", self.debug)
            delay_start = time.time()
            thread.join()
            delay_end = time.time()
            utils.log_warning("Resulting delay of: {0} seconds".format(str(delay_end - delay_start)), self.debug)

    # --------- Main loop function ---------

    def run_loop(self):
        # Set initial configuration
        service_config = utils.MyConfig(self._default_config)

        # Configure service logging
        handler = RotatingFileHandler(filename=self.service_name + ".log", maxBytes=self.MAX_LOG_SIZE, backupCount=self.BACKUP_COUNT)
        logging.basicConfig(level=logging.INFO, format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT, handlers=[handler])

        self.on_start()

        while True:
            # Get configuration from CouchDB and update
            self._update_config(service_config)

            # Do things after config update
            self.on_config_updated(service_config)

            t0 = self._start_epoch()
            self._print_config(service_config)

            # Validate configuration
            invalid, message = self.invalid_conf(service_config)
            if invalid:
                utils.log_error(message, self.debug)

            if not self.active:
                utils.log_warning("{0} is not activated".format(self.service_name.capitalize()), self.debug)

            # Do main work
            thread = None
            if self.active and not invalid:
                thread = self.work()

            # Sleep
            sleep_time = self.compute_sleep_time()
            time.sleep(sleep_time)

            # Wait for thread to finish if exists
            self._wait_operation_thread(thread)

            # End epoch
            self._end_epoch(sleep_time, t0)
