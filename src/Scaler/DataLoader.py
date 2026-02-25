import src.MyUtils.MyUtils as utils


class DataContext:

    def __init__(self, container=None, application=None, user=None, host=None, container_resources=None, container_usages=None):
        self.containers = container or {}
        self.applications = application or {}
        self.users = user or {}
        self.hosts = host or {}
        self.container_resources = container_resources or {}
        self.container_usages = container_usages or {}

    # Compatibility with dict-like functions
    def get(self, key, default=None):
        return getattr(self, key, default)


class DataLoader:

    def __init__(self, couchdb_handler, bdwatchdog_handler, rescaler_session, debug=False):
        self.couchdb_handler = couchdb_handler
        self.bdwatchdog_handler = bdwatchdog_handler
        self.rescaler_session = rescaler_session
        self.debug = debug

        # Data caches
        self._cache = {"container": None, "application": None, "user": None, "host": None, "container_resources": None}

        # Loaded status
        self._loaded = {"container": False, "application": False, "user": False, "host": False, "container_resources": False}

        self.needed_resources = None

    @staticmethod
    def get_structures_types_to_load(requests):
        # Check if there are user-level requests
        if any(r.get("structure_type") == "user" for r in requests):
            return ["user", "application", "container"]
        # Check if there are application-level requests
        if any(r.get("structure_type") == "application" for r in requests):
            return ["application", "container"]

        ## Check if there are container-level requests
        #if any(r.get("structure_type") == "container" for r in requests):
        #    return ["container"]

        return ["container"]

    @staticmethod
    def get_resources_to_load(requests):
        return set([r.get("resource") for r in requests])

    def load_data(self, requests):
        # Save the needed resources and containers just in case BDWatchdog time series are later needed
        self.needed_resources = self.get_resources_to_load(requests)

        # Check which structure types are involved in current requests
        structures_to_load = self.get_structures_types_to_load(requests)
        self.log_info(f"Structures to load based on requests: {structures_to_load}")

        if "container" in structures_to_load:
            # Load containers
            if self._load_structures("container") is None:
                self.log_error("Failed to load containers, cannot proceed")
                return False

            # Load container resources
            if self._load_container_resources() is None:
                self.log_error("Failed to load container resources, cannot proceed")
                return False

            # Hosts are needed to understand container topology
            if self._load_structures("host") is None:
                self.log_error("Failed to load hosts, cannot proceed")
                return False

        if "application" in structures_to_load:
            if self._load_structures("application") is None:
                self.log_error("Failed to load applications, cannot proceed")
                return False

        if "user" in structures_to_load:
            if self._load_structures("user") is None:
                self.log_error("Failed to load users, cannot proceed")
                return False

        if "application" in structures_to_load or "user" in structures_to_load:
            if self._load_container_usages() is None:
                self.log_error("Failed to load container usages, cannot proceed")
                return False

        return True

    def get_data_context(self):
        return DataContext(**{_type: self._cache[_type] for _type in self._cache if self._loaded[_type]})

    def _load_structures(self, structure_type):
        if self._loaded.get(structure_type):
            return self._cache.get(structure_type)

        try:
            self.log_info(f"-> Loading {structure_type}s from CouchDB...")

            data = utils.get_structures(self.couchdb_handler, self.debug, subtype=structure_type)

            if not data:
                self.log_warning(f"No {structure_type} found in CouchDB")
                cache = {}
            else:
                cache = {structure["name"]: structure for structure in data}
                self.log_info(f"Successfully loaded {len(cache)} {structure_type}s")

            self._cache[structure_type] = cache
            self._loaded[structure_type] = True

            return cache

        except Exception as e:
            self.log_error(f"Failed to load {structure_type}s: {str(e)}")
            return None

    def _load_container_resources(self):
        if self._loaded["container_resources"]:
            return self._cache["container_resources"]

        self.log_info(f"-> Loading container resources limits from NodeRescaler...")

        try:
            if not self._loaded["container"]:
                self.log_warning("Must load containers before loading container resources")
                return None

            if not self._cache["container"]:
                self.log_warning("No containers to get NodeRescaler resource limits, skipping")
                self._loaded["container_resources"] = True
                self._cache["container_resources"] = {}
                return self._cache["container_resources"]


            cache = utils.get_container_resources_dict(self._cache["container"], self.rescaler_session, self.debug)

            if not cache:
                self.log_error("Failed to get container resources")
                return None

            self._loaded["container_resources"] = True
            self._cache['container_resources'] = cache

            self.log_info(f"Successfully loaded resources for {len(cache)} containers")
            return cache

        except Exception as e:
            self.log_error(f"Failed to load container resources: {str(e)}")
            return None

    def _load_container_usages(self):
        if self._loaded["container_usages"]:
            return self._cache["container_usages"]

        self.log_info(f"-> Loading container usages from BDWatchdog...")

        try:
            if not self._loaded["container"]:
                self.log_error("Must load containers before loading container usages")
                return None

            if not self._cache["container"]:
                self.log_warning("No containers to get BDWatchdog usages, skipping")
                self._loaded["container_usages"] = True
                self._cache["container_usages"] = {}
                return self._cache["container_usages"]

            metrics_to_retrieve, metrics_to_generate = utils.get_metrics_to_retrieve_and_generate(
                list(self.needed_resources), "container")

            # Get the request usage for all the containers and cache it
            container_usages = {}
            for container_name in self._cache["container"]:
                # TODO: Check if we can do this in a single request
                container_usages[container_name] = self.bdwatchdog_handler.get_structure_timeseries(
                    {"host": container_name}, 10, 20, metrics_to_retrieve, metrics_to_generate)

                # Populate containers cache with usage data
                for resource in self.needed_resources:
                    self._cache["container"][container_name]["resources"][resource]["usage"] = container_usages[container_name][utils.res_to_metric(resource)]

            self._loaded["container_usages"] = True
            self._cache["container_usages"] = container_usages

            self.log_info(f"Successfully loaded usages for {len(container_usages)} containers")
            return container_usages

        except Exception as e:
            self.log_error(f"Failed to load container usages: {str(e)}")
            return None

    def get_all_structures(self, structure_type):
        """Returns all structures of a given type from cache, loading them if necessary"""
        if structure_type not in self._cache:
            self.log_error(f"Invalid structure type '{structure_type}' requested")
            return None

        if not self._loaded[structure_type]:
            if structure_type == "container_resources":
                result = self._load_container_resources()
            elif structure_type == "container_usages":
                result = self._load_container_usages()
            else:
                result = self._load_structures(structure_type)
            if not result:
                self.log_error(f"Failed to load {structure_type}s")
                return None
        return self._cache[structure_type]

    def get_structure(self, structure_type, structure_name):
        """Returns a specific structure from cache, loading it if necessary"""
        if self.get_all_structures(structure_type) is None:
            self.log_error(f"Failed to load {structure_type}s, cannot retrieve {structure_name}")
            return None

        return self._cache[structure_type].get(structure_name)

    def get_all_containers(self):
        return self.get_all_structures("container")

    def get_all_applications(self):
        return self.get_all_structures("application")

    def get_all_users(self):
        return self.get_all_structures("user")

    def get_all_hosts(self):
        return self.get_all_structures("host")

    def get_all_container_resources(self):
        return self.get_all_structures("container_resources")

    def get_all_container_usages(self):
        return self.get_all_structures("container_usages")

    def get_application(self, app_name):
        return self.get_structure("application", app_name)

    def get_user(self, user_name):
        return self.get_structure("user", user_name)

    def get_host(self, host_name):
        return self.get_structure("host", host_name)

    def get_container_resource(self, container_name):
        return self.get_structure("container_resources", container_name)

    def clear_data(self):
        """Clean data caches after each Scaler iteration"""
        for structure_type in self._cache.keys():
            self._cache[structure_type] = None
            self._loaded[structure_type] = False

        self.log_info("DataLoader caches cleared")

    def log_info(self, msg):
        utils.log_info(msg, self.debug)

    def log_error(self, msg):
        utils.log_error(msg, self.debug)

    def log_warning(self, msg):
        utils.log_warning(msg, self.debug)