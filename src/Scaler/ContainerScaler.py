import src.MyUtils.MyUtils as utils
from src.Scaler.BaseScaler import BaseScaler
from src.Scaler.ScalerUtils import ContainerRequest


class ContainerScaler(BaseScaler):
    PARENT_LEVEL = "application"
    CURRENT_LEVEL = "container"

    def check_host_has_enough_free_resources(self, host_name, needed_amount, resource, container):
        # Check host info is available
        host_info = self.data_context.hosts.get(host_name, None)
        if host_info is None:
            self.log_warning("Host {0} not found in data context".format(host_name))
            return False, needed_amount

        # Get free resources in host
        bound_disk = container["resources"].get("disk", {}).get("name")
        if resource in {"disk_read", "disk_write"}:
            disk_op = resource.split("_")[-1]
            host_free = host_info["resources"]["disks"][bound_disk]["free_{0}".format(disk_op)]
        else:
            host_free = host_info["resources"][resource]["free"]

        # If no free resources, scaling cannot be performed
        if host_free == 0:
            self.log_warning("No {0} resources available in host {1} ".format(resource, host_info["name"]))
            return False, needed_amount

        # If not enough free resources, scaling cannot be fully performed, but maybe partially
        if host_free < needed_amount:
            self.log_warning("Not enough {0} free resources in host {1} for container {2}, available {3} needed {4}"
                             .format(resource, host_name, container["name"], host_free, needed_amount))
            return False, needed_amount - host_free

        # If resource is disk, check total free bandwidth
        if resource in {"disk_read", "disk_write"}:
            max_read = host_info["resources"]["disks"][bound_disk]["max_read"]
            max_write = host_info["resources"]["disks"][bound_disk]["max_write"]
            consumed_read = max_read - host_info["resources"]["disks"][bound_disk]["free_read"]
            consumed_write = max_write - host_info["resources"]["disks"][bound_disk]["free_write"]
            current_disk_free = max(max_read, max_write) - consumed_read - consumed_write
            if current_disk_free < needed_amount:
                missing_shares = needed_amount - current_disk_free
                self.log_warning("Beware, there is not enough free total bandwidth for container {0} for resource {1} in"
                                 " the host, there are {2},  missing {3}".format(container["name"], resource, current_disk_free, missing_shares))
                return False, missing_shares

        # Host has enough free resources, scaling can be fully performed
        return True, 0

    def check_container_request(self, container, container_resources, request):
        translation_dict = {"cpu": "cpu_allowance_limit", "mem": "mem_limit", "disk_read": "disk_read_limit",
                            "disk_write": "disk_write_limit", "energy": "energy_limit"}
        resource = request["resource"]
        _min = container["resources"][resource]["min"]
        _current = container["resources"][resource]["current"]
        _max = container["resources"][resource]["max"]
        amount_for_current = request["amount"]


        # MAX SCALING: Check max is above min
        scaled_max_amount = 0
        if request["field"] == "max":
            if _max + request["amount"] < _min:
                scaled_max_amount = _max - _min
                self.log_warning("Container '{0}' cannot be scaled: max would be lower than min (aborting)".format(container["name"]))
            else:
                scaled_max_amount = request["amount"]
            _max += scaled_max_amount
            container["resources"][resource]["max"] = _max
            amount_for_current = _max - _current

            if scaled_max_amount == 0:
                return scaled_max_amount

        # CURRENT SCALING: If "max" was previously scaled, "current" will be adjusted to max
        physical_limit = int(container_resources["resources"][resource].get(translation_dict[resource]))
        if physical_limit is None:
            self.log_warning("Resource '{0}' limit for container '{1}' not found in NodeRescaler info".format(resource, container["name"]))
            return False, 0

        # Trim amount for current if new value would be out of bounds
        new_value = int(physical_limit + amount_for_current)
        if new_value < _min:
            amount_for_current = _min - physical_limit
            self.log_warning("Trimming {0} value, new current {1} would be lower than min {2}".format(resource, new_value, _min))
        elif new_value > _max:
            amount_for_current = _max - physical_limit
            self.log_warning("Trimming {0} value, new current {1} would be higher than max {2}".format(resource, new_value, _max))

        # Check if host has enough free resources for the new current value
        scaled_current_amount = amount_for_current
        if amount_for_current > 0:
            success, missing_shares = self.check_host_has_enough_free_resources(container["host"], amount_for_current, resource, container)
            scaled_current_amount = amount_for_current - missing_shares

        container["resources"][resource]["current"] += scaled_current_amount
        container_resources["resources"][resource][translation_dict[resource]] += scaled_current_amount

        if request["field"] == "max":
            # If "current" scaling comes from a "max" scaling, and "current" could not be adjusted to "max" (due to free
            # host resources limitations), update "max" to the final current level -> should only happen in scale-ups
            if container["resources"][resource]["current"] != container["resources"][resource]["max"]:
                scaled_max_amount -= container["resources"][resource]["max"] - container["resources"][resource]["current"]
                container["resources"][resource]["max"] = container["resources"][resource]["current"]

            return scaled_max_amount
        else:
            return scaled_current_amount

    def plan_operation(self, data_context, operation, swap_part=None):
        data_to_update = {"containers": {}, "container_resources": {}}

        # Get info from operation
        op_type, resource = operation.op_type, operation.resource
        amount, structure_name = self._get_amount_and_structure(operation, swap_part)
        field, priority = operation.field, operation.priority

        # Get structures from data context
        container = data_context.containers[structure_name]
        container_resources = data_context.container_resources[structure_name]

        # Generate container request
        container_request = utils.generate_request(container, amount, resource, priority, field)

        # Check container request can be fully performed
        scaled_amount = self.check_container_request(container, container_resources, container_request)
        if self.op_should_be_aborted(op_type, container_request, scaled_amount):
            return False, [], None
        self.update_request(container_request, scaled_amount)

        # Create final container request and set data that has been updated
        final_requests = [ContainerRequest(container_request, self.couchdb_handler, self.rescaler_session, self.debug)]
        data_to_update["containers"][structure_name] = container
        data_to_update["container_resources"][structure_name] = container_resources

        return True, final_requests, data_to_update
