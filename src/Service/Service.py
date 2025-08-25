import time
import logging
from threading import Thread

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb


class Service:
    """Base class for all services."""

    def __init__(self, service_name, config_validator, default_config, sleep_attr="polling_frequency"):
        self.service_name = service_name
        self.config_validator = config_validator
        self._default_config = default_config
        self._sleep_attr = sleep_attr  # e.g. "polling_frequency" or "window_timelapse"
        self.couchdb_handler = couchdb.CouchDBServer()
        self.active, self.debug = None, None

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

    # --------- Auxiliar functions ---------

    def _get_sleep_time(self, ):
        val = getattr(self, self._sleep_attr, None)
        if val is None:
            raise AttributeError(f"Sleep attribute '{self._sleep_attr}' not found on {self}")
        return val

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

    # --------- Main loop function ---------

    def run_loop(self):
        service_config = utils.MyConfig(self._default_config)

        logging.basicConfig(filename=self.service_name + ".log", level=logging.INFO,
                            format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT)

        self.on_start()

        while True:
            self._update_config(service_config)

            self.on_config_updated(service_config)

            t0 = utils.start_epoch(self.debug)
            self._print_config(service_config)

            invalid, message = self.invalid_conf(service_config)
            if invalid:
                utils.log_error(message, self.debug)

            if not self.active:
                utils.log_warning("{0} is not activated".format(self.service_name.capitalize()), self.debug)

            thread = None
            if self.active and not invalid:
                thread = self.work()

            # Sleep
            sleep_time = self._get_sleep_time()
            time.sleep(sleep_time)

            # Wait for thread to finish if exists
            utils.wait_operation_thread(thread, self.debug)

            # End epoch
            utils.end_epoch(self.debug, sleep_time, t0)
