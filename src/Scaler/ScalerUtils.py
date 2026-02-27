import json
from requests import HTTPError
from threading import Thread

import src.MyUtils.MyUtils as utils


class ResourceOperation:

    def __init__(self, op_type, scope, request, donor, receiver, resource, field, amount, priority=0):
        self.op_type = op_type  # SCALE_UP, SCALE_DOWN or SWAP
        self.scope = scope
        self.donor = donor
        self.receiver = receiver
        self.resource = resource
        self.field = field
        self.amount = abs(amount)
        self.priority = priority
        self._original_request = request
        self._generated_requests = {"container": [], "application": [], "user": []}
        self._executed_requests = {"container": [], "application": [], "user": []}

    def __repr__(self):
        unit = {"cpu": "shares", "mem": "B", "disk": "Mbit", "energy": "W"}
        return "OPERATION: @{0} @{1} @{2} {3} @{4} -> @{5}".format(
            self.op_type, self.resource, self.amount, unit[self.resource], self.donor, self.receiver)

    # Compatibility with dict-like functions
    def get(self, key, default=None):
        return getattr(self, key, default)

    @property
    def original_request(self):
        return self._original_request

    @property
    def generated_requests(self):
        return self._generated_requests

    @property
    def all_requests(self):
        return self._generated_requests["container"] + self._generated_requests["application"] + self._generated_requests["user"]

    @property
    def container_requests(self):
        return self._generated_requests["container"]

    @property
    def application_requests(self):
        return self._generated_requests["application"]

    @property
    def user_requests(self):
        return self._generated_requests["user"]

    @property
    def executed_requests(self):
        return self._executed_requests

    @property
    def container_executed_requests(self):
        return self._executed_requests["container"]

    @property
    def application_executed_requests(self):
        return self._executed_requests["application"]

    @property
    def user_executed_requests(self):
        return self._executed_requests["user"]

    def add_request(self, request):
        if not isinstance(request, StructureRequest):
            raise TypeError("Adding request to operation. Expected StructureRequest, got {0}".format(type(request).__name__))
        self._generated_requests[request.get_type()].append(request)

    def add_requests(self, requests):
        for request in requests:
            self.add_request(request)

    def set_generated_requests(self, value):
        if not isinstance(value, list):
            raise TypeError("generated_requests must be a list")
        if not all(isinstance(r, StructureRequest) for r in value):
            raise TypeError("All elements of generated_requests must be StructureRequest instances")
        self._generated_requests = value

    def mark_request_executed(self, request):
        self._generated_requests[request.get_type()].remove(request)
        self._executed_requests[request.get_type()].append(request)

    def remove_request_executed(self, request):
        self._executed_requests[request.get_type()].remove(request)
        self._generated_requests[request.get_type()].append(request)


class StructureRequest:
    TYPE = None
    TRANSLATION_DICT = {"cpu": "cpu_allowance_limit", "mem": "mem_limit", "disk_read": "disk_read_limit",
                        "disk_write": "disk_write_limit", "energy": "energy_limit"}

    def __init__(self, request, couchdb_handler, rescaler_session, debug=False):
        self._request = request
        self.structure_name = request["structure"]
        self.amount = request["amount"]
        self.field = request["field"]
        self.couchdb_handler = couchdb_handler
        self.rescaler_session = rescaler_session
        self.debug = debug
        self.applied = False

    def __repr__(self):
        unit = {"cpu": "shares", "mem": "B", "disk": "Mbit", "energy": "W"}
        return "{0} REQUEST: @{1} @{2} {3} @{4}".format(
            self.TYPE.upper(), self._request["resource"], self.amount, unit[self._request["resource"]], self.structure_name)

    @property
    def request(self):
        return self._request

    # Compatibility with dict-like functions
    def get(self, key, default=None):
        return getattr(self, key, default)

    def get_type(self):
        return self.TYPE

    def translate(self, resource):
        return self.TRANSLATION_DICT.get(resource, "{0}_limit".format(resource))

    def log_info(self, msg: str):
        utils.log_info(msg, self.debug)

    def log_error(self, msg: str):
        utils.log_error(msg, self.debug)

    def log_warning(self, msg: str):
        utils.log_warning(msg, self.debug)

    def update_max_in_couchdb(self, resource, amount, database_resources):
        # Calculate new 'max' value
        new_value = database_resources["resources"][resource]["max"] + amount

        # Update 'max' in CouchDB
        thread = Thread(name="update_{0}".format(database_resources["name"]), target=utils.update_resource_in_couchdb,
                        args=(database_resources, resource, "max", new_value, self.couchdb_handler, False),
                        kwargs={"max_tries": 5, "backoff_time_ms": 500})
        thread.start()

        return thread

    def execute(self, data_context, **kwargs):
        #thread = None
        try:
            resource = self._request["resource"]

            # Get structure info from data context
            structure = getattr(data_context, self.TYPE + "s", {}).get(self.structure_name, {})
            old_value = structure["resources"][resource]["max"]
            new_value = old_value + self.amount
            #thread = self.update_max_in_couchdb(resource, amount, structure)
            utils.update_resource_in_couchdb(structure, resource, "max", new_value,
                                             self.couchdb_handler, False,
                                             max_tries=5, backoff_time_ms=500)

            # Update 'max' value in data context for future requests
            structure["resources"][resource]["max"] = new_value

            self.log_info("@{0} @{1} @max  {2} -> {3}".format(self.structure_name, resource, old_value, new_value))

            self.applied = True
        except Exception as e:
            self.log_error("Error executing request: {0} -> {1}".format(self._request, str(e)))
            return False

        return True

    def rollback(self, data_context, **kwargs):
        if self.applied:
            self.amount= -self.amount
            success = self.execute(data_context, **kwargs)
            self.amount = -self.amount  # revert the amount change for future rollbacks if needed
            if success:
                self.log_info("Rollback successful for request: {0} and structure: {1}".format(self._request["action"], self.structure_name))
            else:
                self.log_warning("Rollback failed for request: {0} and structure: {1}".format(self._request["action"], self.structure_name))
            return success
        raise ValueError("Cannot rollback a request that was not successfully applied")


class UserRequest(StructureRequest):
    TYPE = "user"

    def execute(self, data_context, **kwargs):
        if self._request["field"] != "max":
            self.log_warning("Only 'max' scalings are supported for users. Skipping request: {0}".format(self._request))
            return False

        return super().execute(data_context, **kwargs)


class ApplicationRequest(StructureRequest):
    TYPE = "application"

    def execute(self, data_context, **kwargs):
        if self._request["field"] != "max":
            self.log_warning("Only 'max' scalings are supported for applications. Skipping request: {0}".format(self._request))
            return False

        return super().execute(data_context, **kwargs)


class ContainerRequest(StructureRequest):
    TYPE = "container"

    def __init__(self, request, couchdb_handler, rescaler_session, debug=False):
        super().__init__(request, couchdb_handler, rescaler_session, debug)
        if "host" not in request:
            raise ValueError("Host must be specified in container requests")
        self.host = request["host"]
        self.apply_request_by_resource = {
            "cpu": self.apply_cpu_request, "mem": self.apply_mem_request,
            "disk_read": self.apply_disk_read_request, "disk_write": self.apply_disk_write_request,
            "energy": self.apply_energy_request, "net": self.apply_net_request
        }
        self.host_changes, self.host_lock = None, None

    def _get_resource_phy_limit(self, data_context, container_name, resource):
        return int(data_context.container_resources.get(container_name, {}).get("resources", {}).get(resource, {}).get(self.translate(resource)))

    @staticmethod
    def _get_cpu_list(cpu_num_string):
        # Translate something like '2-4,7' to [2,3,7]
        cpu_list = list()
        parts = cpu_num_string.split(",")
        for part in parts:
            ranges = part.split("-")
            if len(ranges) == 1:
                cpu_list.append(ranges[0])
            else:
                for n in range(int(ranges[0]), int(ranges[1]) + 1):
                    cpu_list.append(str(n))
        return cpu_list

    @staticmethod
    def _generate_core_dist(topology, dist_name):
        core_dist = []
        supported_distributions = {"Group_P&L", "Group_1P_2L", "Group_PP_LL", "Spread_P&L", "Spread_PP_LL"}
        if dist_name not in supported_distributions:
            raise ValueError("Invalid core distribution: {0}. Supported: {1}.".format(dist_name, supported_distributions))

        # Pairs of physical and logical cores, one socket at a time
        if dist_name == "Group_P&L":
            for sk_id in topology:
                for core_id in topology[sk_id]:
                    core_dist.extend(topology[sk_id][core_id])

        # First physical cores, then logical cores, one socket at a time
        if dist_name == "Group_1P_2L":
            for sk_id in topology:
                phy_c, log_c = [], []
                for core_id in topology[sk_id]:
                    phy_c.append(topology[sk_id][core_id][0])
                    log_c.extend(topology[sk_id][core_id][1:])
                core_dist.extend(phy_c)
                core_dist.extend(log_c)

        # First physical cores, from both sockets, then logical cores
        if dist_name == "Group_PP_LL":
            phy_c, log_c = [], []
            for sk_id in topology:
                for core_id in topology[sk_id]:
                    phy_c.append(topology[sk_id][core_id][0])
                    log_c.extend(topology[sk_id][core_id][1:])
            core_dist.extend(phy_c)
            core_dist.extend(log_c)

        # Pairs of physical and logical cores, alternating between sockets
        if dist_name == "Spread_P&L":
            other_sk = sorted(topology, key=lambda sk: len(topology[sk]))
            sk_id = other_sk.pop()
            for core_id in topology[sk_id]:
                core_dist.extend(topology[sk_id][core_id])
                for sk2_id in other_sk:
                    core_dist.extend(topology[sk2_id].get(core_id, []))

        # First physical cores, then logical cores, alternating between sockets
        if dist_name == "Spread_PP_LL":
            other_sk = sorted(topology, key=lambda sk: len(topology[sk]))
            sk_id = other_sk.pop()
            phy_c, log_c = [], []
            for core_id in topology[sk_id]:
                phy_c.append(topology[sk_id][core_id][0])
                log_c.extend(topology[sk_id][core_id][1:])
                for sk2_id in other_sk:
                    phy_c.extend(topology[sk2_id].get(core_id, [])[0:1])
                    log_c.extend(topology[sk2_id][core_id][1:])
            core_dist.extend(phy_c)
            core_dist.extend(log_c)

        return [str(c) for c in core_dist]

    @staticmethod
    def _scale_cpu(core_usage_map, take_core_list, used_cores, structure_name, amount, scale_up=True):
        # When scaling up, we take shares from 'free' and put them into the structure_name
        # when scaling down, we take shares from the structure_name and put them into 'free'
        from_key = "free" if scale_up else structure_name
        to_key = structure_name if scale_up else "free"

        original_amount = amount
        for core in take_core_list:
            if amount <= 0:
                break
            if core_usage_map.get(core, {}).get(from_key, 0) > 0:
                take = min(core_usage_map[core][from_key], amount)
                core_usage_map[core][from_key] -= take
                core_usage_map[core][to_key] += take
                amount -= take

                # If we are scaling up, we add the core to the used_cores list if it is not already there
                if scale_up:
                    if core not in used_cores:
                        used_cores.append(core)
                # If we are scaling down, we remove the core from used_cores if it has no shares left
                else:
                    if core_usage_map[core][structure_name] == 0 and core in used_cores:
                        used_cores.remove(core)
        return amount, original_amount - amount

    def _get_cpu_topology(self, container):
        rescaler_ip = container["host_rescaler_ip"]
        rescaler_port = container["host_rescaler_port"]
        r = self.rescaler_session.get("http://{0}:{1}/host/cpu_topology".format(rescaler_ip, rescaler_port),
                                      headers={'Accept': 'application/json'})
        if r.status_code == 200:
            return dict(r.json())

        self.log_error("Error getting CPU topology from host in IP {0}".format(rescaler_ip))
        r.raise_for_status()

    def apply_cpu_request(self, request, amount, data_context):
        container_name, resource = request["structure"], request["resource"]

        # Get container info from NodeRescaler
        cont_phy_resources = data_context.container_resources.get(container_name, {})
        current_cpu_limit = self._get_resource_phy_limit(data_context, container_name, resource)
        container_cpu_list = self._get_cpu_list(cont_phy_resources["resources"]["cpu"]["cpu_num"])
        used_cores = list(container_cpu_list)  # copy

        # Get CPU topology from host and generate core distribution
        cpu_topology = self._get_cpu_topology(request)
        # TODO: Add core_distribution as a tunable service parameter
        core_distribution = self._generate_core_dist(cpu_topology, "Group_PP_LL")

        # Using lock to read and update host free resources
        with self.host_lock:
            # Get host info from data context
            host_info = data_context.hosts.get(request["host"])
            core_usage_map = host_info["resources"][resource]["core_usage_mapping"]
            host_max_cores = int(host_info["resources"]["cpu"]["max"] / 100)
            host_cpu_list = [str(i) for i in range(host_max_cores)]
            for core in host_cpu_list:
                core_usage_map.setdefault(core, {"free": 100})
                core_usage_map[core].setdefault(container_name, 0)

            # RESCALE UP
            if amount > 0:
                needed_shares = amount

                # 1) Fill first the already used cores following core distribution order
                used_cores_sorted = [c for c in core_distribution if c in used_cores]
                needed_shares, assigned = self._scale_cpu(core_usage_map, used_cores_sorted, used_cores, container_name, needed_shares)

                # 2) Fill the completely free cores following core distribution order
                completely_free_cores = [c for c in core_distribution if c not in used_cores and core_usage_map[c]["free"] == 100]
                needed_shares, assigned = self._scale_cpu(core_usage_map, completely_free_cores, used_cores, container_name, needed_shares)

                # 3) Fill the remaining cores that are not completely free, following core distribution order
                remaining_cores = [c for c in core_distribution if c not in used_cores and core_usage_map[c]["free"] < 100]
                needed_shares, assigned = self._scale_cpu(core_usage_map, remaining_cores, used_cores, container_name, needed_shares)

                if needed_shares > 0:
                    self.log_warning("Container {0} couldn't get as much CPU shares as intended ({1}), instead it got {2}"
                                      .format(container_name, amount, amount - needed_shares))
                    amount = amount - needed_shares

            # RESCALE DOWN
            elif amount < 0:
                shares_to_free = abs(amount)

                # Sort cores by reverse core distribution order
                rev_core_distribution = list(reversed(core_distribution))
                used_cores_sorted = [c for c in rev_core_distribution if c in used_cores]

                # 1) Free cores starting with the least used ones and following reverse core distribution order
                least_used_cores = sorted(used_cores_sorted, key=lambda c: core_usage_map[c][container_name])
                shares_to_free, freed = self._scale_cpu(core_usage_map, least_used_cores, used_cores, container_name, shares_to_free, scale_up=False)

                if shares_to_free > 0:
                    raise ValueError("Error in setting cpu, couldn't free the resources properly")

            # No error thrown, so persist the new mapping to the cache
            host_info["resources"]["cpu"]["core_usage_mapping"] = core_usage_map
            host_info["resources"]["cpu"]["free"] -= amount
            self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("cpu", {})["core_usage_mapping"] = core_usage_map
            self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("cpu", {})["free"] = host_info["resources"]["cpu"]["free"]

        # Return the dictionary to set new resources through NodeRescaler
        return {"cpu": {"cpu_num": ",".join(used_cores), "cpu_allowance_limit": int(current_cpu_limit + amount)}}

    def apply_mem_request(self, request, amount, data_context):
        container_name, resource = request["structure"], request["resource"]
        current_mem_limit = self._get_resource_phy_limit(data_context, container_name, resource)

        with self.host_lock:
            host_info = data_context.hosts.get(request["host"])
            host_mem_free = host_info["resources"]["mem"]["free"]
            amount = min(amount, host_mem_free)

            # No error thrown, so persist the new mapping to the cache
            host_info["resources"]["mem"]["free"] -= amount
            self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("mem", {})["free"] = host_info["resources"]["mem"]["free"]

        # Return the dictionary to set new resources through NodeRescaler
        return {"mem": {"mem_limit": str(int(amount + current_mem_limit))}}

    def apply_disk_read_request(self, request, amount, data_context):
        container_name, resource = request["structure"], request["resource"]
        current_read_limit = self._get_resource_phy_limit(data_context, container_name, resource)
        bound_disk = data_context.containers.get(container_name)["resources"].get("disk", {}).get("name")

        with self.host_lock:
            # Get host info from data context
            host_info = data_context.hosts.get(request["host"])
            current_read_free = host_info["resources"]["disks"][bound_disk]["free_read"]
            current_write_free = host_info["resources"]["disks"][bound_disk]["free_write"]

            amount = min(amount, current_read_free)  # Available read bandwidth

            max_read = host_info["resources"]["disks"][bound_disk]["max_read"]
            max_write = host_info["resources"]["disks"][bound_disk]["max_write"]
            consumed_read = max_read - current_read_free
            consumed_write = max_write - current_write_free
            current_disk_free = max(max_read, max_write) - consumed_read - consumed_write

            amount = min(amount, current_disk_free)  # Total available bandwidth

            # No error thrown, so persist the new mapping to the cache
            host_info["resources"]["disks"][bound_disk]["free_read"] -= amount
            self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("disks", {}).setdefault(bound_disk, {})["free_read"] = host_info["resources"]["disks"][bound_disk]["free_read"]

        # Return the dictionary to set the resources
        return {"disk_read": {"disk_read_limit": str(int(amount + current_read_limit))}}

    def apply_disk_write_request(self, request, amount, data_context):
        container_name, resource = request["structure"], request["resource"]
        current_write_limit = self._get_resource_phy_limit(data_context, container_name, resource)
        bound_disk = data_context.containers.get(container_name)["resources"].get("disk", {}).get("name")

        with self.host_lock:
            # Get host info from data context
            host_info = data_context.hosts.get(request["host"])
            current_read_free = host_info["resources"]["disks"][bound_disk]["free_read"]
            current_write_free = host_info["resources"]["disks"][bound_disk]["free_write"]

            amount = min(amount, current_write_free)  # Available write bandwidth

            max_read = host_info["resources"]["disks"][bound_disk]["max_read"]
            max_write = host_info["resources"]["disks"][bound_disk]["max_write"]
            consumed_read = max_read - current_read_free
            consumed_write = max_write - current_write_free
            current_disk_free = max(max_read, max_write) - consumed_read - consumed_write

            amount = min(amount, current_disk_free)  # Total available bandwidth

            # No error thrown, so persist the new mapping to the cache
            host_info["resources"]["disks"][bound_disk]["free_write"] -= amount
            self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("disks", {}).setdefault(bound_disk, {})["free_write"] = host_info["resources"]["disks"][bound_disk]["free_write"]

        # Return the dictionary to set the resources
        return {"disk_read": {"disk_write_limit": str(int(amount + current_write_limit))}}

    def apply_energy_request(self, request, amount, data_context):
        container_name, resource = request["structure"], request["resource"]
        current_energy_limit = self._get_resource_phy_limit(data_context, container_name, resource)

        with self.host_lock:
            host_info = data_context.hosts.get(request["host"])
            host_energy_free = host_info["resources"]["energy"]["free"]

            amount = min(amount, host_energy_free)

            # No error thrown, so persist the new mapping to the cache
            host_info["resources"]["energy"]["free"] -= amount
            self.host_changes.setdefault(request["host"], {}).setdefault("resources", {}).setdefault("energy", {})["free"] = host_info["resources"]["energy"]["free"]

        # Return the dictionary to set the resources
        return {"energy": {"energy_limit": str(int(current_energy_limit + amount))}}

    def apply_net_request(self, request, amount, data_context):
        container_name, resource = request["structure"], request["resource"]
        current_net_limit = self._get_resource_phy_limit(data_context, container_name, resource)

        # Return the dictionary to set the resources
        return {"net": {"net_limit": str(int(amount + current_net_limit))}}

    def execute(self, data_context, **kwargs):

        try:
            # Get host changes and lock from kwargs, needed to update host free resources when applying the request
            if "host_changes" not in kwargs:
                raise ValueError("Host changes dictionary must be provided in kwargs to execute a container request")
            if "host_lock" not in kwargs:
                raise ValueError("Host lock must be provided in kwargs to execute a container request")
            self.host_changes = kwargs["host_changes"]
            self.host_lock = kwargs["host_lock"]

            couchdb_thread = None
            resource, field = self._request["resource"], self._request["field"]
            container = data_context.containers.get(self.structure_name, {})
            amount_for_current = int(self.amount)

            # If 'max' is changed it is updated in CouchDB and 'current' is adjusted accordingly
            if field == "max":
                amount = amount_for_current
                _max = container["resources"][resource]["max"]
                _current = self._get_resource_phy_limit(data_context, self.structure_name, resource)
                # CAUTION!! This method updates container dictionary in data context, don't update "max" twice
                couchdb_thread = self.update_max_in_couchdb(resource, amount, container)

                # Print max scaling info
                self.log_info("@{0} @{1} @max  {2} -> {3}".format(self.structure_name, resource, _max, _max + amount))

                # If max is changed, 'current' will always be adjusted to max
                amount_for_current = (_max + amount) - _current

            # Update container "current" value getting host free resources
            new_resources = self.apply_request_by_resource[resource](self._request, amount_for_current, data_context)
            if new_resources:
                # Apply changes through a REST call to NodeRescaler
                utils.set_container_physical_resources(self.rescaler_session, container, new_resources, self.debug)

                old_value = self._get_resource_phy_limit(data_context, self.structure_name, resource)
                new_value = new_resources[resource][self.translate(resource)]
                self.log_info("@{0} @{1} @current {2} -> {3}".format(self.structure_name, resource, old_value, new_value))

                # Update container in data context (useful if there are multiple requests for the same container)
                data_context.container_resources[self.structure_name]["resources"][resource] = new_resources[resource]

            if couchdb_thread:
                couchdb_thread.join()  # Wait for the CouchDB update to finish before marking the request as applied

            self.applied = True
        except ValueError as e:
            self.log_error("Error with container {0} during request application -> {1}".format(self.structure_name, str(e)))
            return False
        except HTTPError as e:
            self.log_error("Error setting container {0} resources -> {1}".format(self.structure_name, str(e)))
            return False
        except Exception as e:
            self.log_error("Error with container {0} -> {1}".format(self.structure_name, str(e)))
            return False

        return True
