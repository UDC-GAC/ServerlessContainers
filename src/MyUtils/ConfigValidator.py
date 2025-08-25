from functools import partial


class ConfigValidator:

    def __init__(self, min_frequency=5, min_timeout=5, min_delay=5):
        self.min_frequency = min_frequency
        self.min_timeout = min_timeout
        self.min_delay = min_delay
        self.allowed_resources = {"cpu", "mem", "disk_read", "disk_write", "net", "energy"}
        self.allowed_structures = {"container", "application", "user"}
        self.validators = {
            # Numeric checkers
            "POLLING_FREQUENCY": partial(self._check_min, self.min_frequency),
            "WINDOW_TIMELAPSE": partial(self._check_min, self.min_frequency),
            "WINDOW_DELAY": partial(self._check_min, self.min_delay),
            "EVENT_TIMEOUT": partial(self._check_min, self.min_timeout),
            "REQUEST_TIMEOUT": partial(self._check_min, self.min_timeout),
            # Resource checkers
            "GUARDABLE_RESOURCES": partial(self._check_values_in_set, self.allowed_resources),
            "RESOURCES_BALANCED": partial(self._check_values_in_set, self.allowed_resources),
            "GENERATED_METRICS": partial(self._check_values_in_set, self.allowed_resources),
            # Structure checkers
            "STRUCTURE_GUARDED": partial(self._check_value_in_set, self.allowed_structures),
            "STRUCTURES_BALANCED": partial(self._check_values_in_set, self.allowed_structures),
            "STRUCTURES_REFEEDED": partial(self._check_values_in_set, self.allowed_structures),
        }

    @staticmethod
    def _check_min(min_value, key, value):
        if value is None:
            return True, "Configuration item '{0}' is likely to be invalid: {1}".format(key, value)

        try:
            if int(value) < min_value:
                return True, "Configuration item '{0}' is lower than its minimum: {1} < {2}".format(key, value, min_value)
        except (ValueError, TypeError):
            return True, "Configuration item '{0}' must be numeric, got '{1}'".format(key, value)

        return False, ""

    @staticmethod
    def _check_values_in_set(allowed_set, key, values):
        if values is None:
            return True, "Configuration item '{0}' is likely to be invalid, got '{1}'".format(key, values)

        if not isinstance(values, (list, set)):
            return True, "Configuration item '{0}' must be a list or a set, got '{1}'".format(key, type(values))

        for v in values:
            if v not in allowed_set:
                return True, "Value '{0}' from configuration item '{1}' is invalid".format(v, key)

        return False, ""

    @staticmethod
    def _check_value_in_set(allowed_set, key, value):
        return ConfigValidator._check_values_in_set(allowed_set, key, [value])

    def invalid_conf(self, config):
        for key, value in config.get_config().items():
            validator = self.validators.get(key)
            if not validator:
                continue
            is_invalid, msg = validator(key, value)
            if is_invalid:
                return True, msg

        return False, ""
