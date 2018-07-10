# /usr/bin/python
from __future__ import print_function

import math

import StateDatabase.couchDB as couchDB
import MyUtils.MyUtils as MyUtils
import json
import time
import requests
import traceback
import logging
import StateDatabase.bdwatchdog as bdwatchdog

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "REQUEST_TIMEOUT": 600, "DEBUG": True}
SERVICE_NAME = "scaler"
db_handler = couchDB.CouchDBServer()
bdwatchdog_handler = bdwatchdog.BDWatchdog()
debug = True

BDWATCHDOG_CONTAINER_METRICS = {"cpu": ['proc.cpu.user', 'proc.cpu.kernel'],
                                "mem": ['proc.mem.resident', 'proc.mem.virtual']}
RESCALER_CONTAINER_METRICS = {
    'cpu': ['proc.cpu.user', 'proc.cpu.kernel'],
    'mem': ['proc.mem.resident']}

host_info_cache = dict()


def filter_requests(request_timeout):
    fresh_requests, final_requests = list(), list()
    all_requests = db_handler.get_requests()

    # First purge the old requests
    for request in all_requests:
        if request["timestamp"] < time.time() - request_timeout:
            db_handler.delete_request(request)
        else:
            fresh_requests.append(request)

    # Then remove repeated requests for the same structure if found
    structure_requests_dict = dict()
    for request in fresh_requests:
        structure = request["structure"]  # The structure name (string), acting as an id
        action = request["action"]  # The action name (string)
        if structure not in structure_requests_dict:
            structure_requests_dict[structure] = dict()

        if action in structure_requests_dict[structure]:
            # A previouse request was found for this structure, remove old one and leave the newer one
            stored_request = structure_requests_dict[structure][action]
            if stored_request["timestamp"] > request["timestamp"]:
                # The stored request is newer, leave it and remove the retrieved one
                db_handler.delete_request(request)
            else:
                # The stored request is older, remove it and save the retrieved one
                db_handler.delete_request(stored_request)
                structure_requests_dict[structure][action] = request
        else:
            structure_requests_dict[structure][action] = request

    for structure in structure_requests_dict:
        key = structure_requests_dict[structure].keys()[0]
        final_requests.append(structure_requests_dict[structure][key])

    return final_requests


# Tranlsate something like '2-4,7' to [2,3,7]
def get_cpu_list(cpu_num_string):
    cpu_list = list()
    parts = cpu_num_string.split(",")
    for part in parts:
        ranges = part.split("-")
        if len(ranges) == 1:
            cpu_list.append(ranges[0])
        else:
            for subpart in ranges:
                cpu_list.append(subpart)
    return cpu_list


def apply_cpu_request(request, database_resources, real_resources, amount):
    global host_info_cache
    resource = request["resource"]
    resource_dict = {resource: {}}
    structure_name = request["structure"]
    host_info = host_info_cache[request["host"]]
    current_cpu_limit = get_current_resource_value(database_resources, real_resources, resource)
    core_usage_map = host_info["resources"][resource]["core_usage_mapping"]

    host_max_cores = int(host_info["resources"]["cpu"]["max"] / 100)
    host_cpu_list = [str(i) for i in range(host_max_cores)]
    for core in host_cpu_list:
        if core not in core_usage_map:
            core_usage_map[core] = dict()
            core_usage_map[core]["free"] = 100
        if structure_name not in core_usage_map[core]:
            core_usage_map[core][structure_name] = 0

    cpu_list = MyUtils.get_cpu_list(real_resources["cpu"]["cpu_num"])
    used_cores = list(cpu_list)  # copy

    if amount > 0:
        # Rescale up, so look for free shares to assign and maybe add cores
        needed_shares = amount

        # First fill the already used cores so that no additional cores are added unnecesarily
        for core in cpu_list:
            if core_usage_map[core]["free"] > 0:
                if core_usage_map[core]["free"] > needed_shares:
                    core_usage_map[core]["free"] -= needed_shares
                    core_usage_map[core][structure_name] += needed_shares
                    needed_shares = 0
                    break
                else:
                    core_usage_map[core][structure_name] += core_usage_map[core]["free"]
                    needed_shares -= core_usage_map[core]["free"]
                    core_usage_map[core]["free"] = 0

        # Next try to satisfy the request adding cores
        if needed_shares > 0:
            # First try looking for a single core with enough shares to fill the request
            for core in host_cpu_list:
                if core_usage_map[core]["free"] >= needed_shares:
                    core_usage_map[core]["free"] -= needed_shares
                    core_usage_map[core][structure_name] += needed_shares
                    needed_shares = 0
                    used_cores.append(core)
                    break

        # Finally, if unsuccessful, use as many cores as neccessary
        if needed_shares > 0:
            for core in host_cpu_list:
                if core_usage_map[core]["free"] > 0:
                    core_usage_map[core][structure_name] += core_usage_map[core]["free"]
                    needed_shares -= core_usage_map[core]["free"]
                    core_usage_map[core]["free"] = 0
                    used_cores.append(core)

        if needed_shares > 0:
            raise ValueError("Error in setting cpu, couldn't get the resources needed")
            # FIXME couldn't do rescale up properly as shares to free remain

    elif amount < 0:
        # Rescale down so free all shares and claim new one to see how many cores can be freed
        shares_to_free = abs(amount)

        # First try to find cores with less shares ('little' ones) and remove them
        for core in reversed(cpu_list):
            if core_usage_map[core][structure_name] <= shares_to_free:
                core_usage_map[core]["free"] += core_usage_map[core][structure_name]
                shares_to_free -= core_usage_map[core][structure_name]
                core_usage_map[core][structure_name] = 0
                used_cores.remove(core)

        # Next, free shares from the remaining cores, the 'big' ones
        if shares_to_free > 0:
            for core in reversed(cpu_list):
                if core_usage_map[core][structure_name] > shares_to_free:
                    core_usage_map[core]["free"] += shares_to_free
                    core_usage_map[core][structure_name] -= shares_to_free
                    shares_to_free = 0
                    break

        if shares_to_free > 0:
            raise ValueError("Error in setting cpu, couldn't free the resources properly")

    # No error thrown, so persist the new mapping to the cache
    host_info_cache[request["host"]]["resources"]["cpu"]["core_usage_mapping"] = core_usage_map
    host_info_cache[request["host"]]["resources"]["cpu"]["free"] -= amount

    # Return the dictionary to set the resources
    resource_dict["cpu"]["cpu_num"] = ",".join(used_cores)
    resource_dict["cpu"]["cpu_allowance_limit"] = int(current_cpu_limit + amount)

    return resource_dict


def apply_mem_request(request, database_resources, real_resources, amount):
    resource_dict = {request["resource"]: {}}
    current_mem_limit = get_current_resource_value(database_resources, real_resources, request["resource"])

    # No error thrown, so persist the new mapping to the cache
    host_info_cache[request["host"]]["resources"]["mem"]["free"] -= amount

    # Return the dictionary to set the resources
    resource_dict["mem"]["mem_limit"] = str(int(amount + current_mem_limit))

    return resource_dict


def apply_disk_request(request, database_resources, real_resources, amount):
    # TODO implement disk rescaling
    resource_dict = {request["resource"]: {}}
    return resource_dict


def apply_net_request(request, database_resources, real_resources, amount):
    # TODO implement net rescaling
    resource_dict = {request["resource"]: {}}
    return resource_dict


def check_invalid_resource_value(database_resources, amount, value, resource):
    max_resource_limit = int(database_resources["resources"][resource]["max"])
    min_resource_limit = int(database_resources["resources"][resource]["min"])
    resource_limit = int(value + amount)

    if resource_limit < 0:
        raise ValueError("Error in setting " + resource + ", it would be lower than 0")
    elif resource_limit < min_resource_limit:
        raise ValueError("Error in setting " + resource + ", it would be lower than min")
    elif resource_limit > max_resource_limit:
        raise ValueError("Error in setting " + resource + ", it would be higher than max")


def get_current_resource_value(database_resources, real_resources, resource):
    translation_dict = {"cpu": "cpu_allowance_limit", "mem": "mem_limit"}
    current_resource_limit = real_resources[resource][translation_dict[resource]]
    if current_resource_limit == -1:
        # RESOURCE is set to unlimited so report min, max or mean, so later apply a rescaling
        # current_resource_limit = database_resources["resources"][resource]["max"]  # Start with max resources
        # current_resource_limit = database_resources["resources"][resource]["min"] # Start with min resources
        current_resource_limit = int(
            database_resources["resources"][resource]["max"] - database_resources["resources"][resource]["min"]) / 2
    else:
        try:
            current_resource_limit = int(current_resource_limit)
        except ValueError:
            raise ValueError("Bad current " + resource + " limit value")
    return current_resource_limit


def check_host_has_enough_free_resources(host_info, needed_resources, resource):
    if host_info["resources"][resource]["free"] < needed_resources:
        raise ValueError("Error in setting " + resource + ", couldn't get the resources needed")


def apply_request(request, real_resources, database_resources):
    global host_info_cache

    amount = int(request["amount"])

    host_info = host_info_cache[request["host"]]
    resource = request["resource"]

    # Get the current resource limit, if unlimited, then max, min or mean
    current_resource_limit = get_current_resource_value(database_resources, real_resources, resource)

    # Check that the memory limit is valid, not lower than min or higher than max
    check_invalid_resource_value(database_resources, amount, current_resource_limit, resource)

    if amount > 0:
        # If the request is for scale up, check that the host has enough free resources before proceeding
        check_host_has_enough_free_resources(host_info, amount, resource)

    return apply_request_by_resource[resource](request, database_resources, real_resources, amount)


def set_container_resources(container, node_rescaler_endpoint, resources):
    r = requests.put("http://" + node_rescaler_endpoint + ":8000/container/" + container, data=json.dumps(resources),
                     headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    if r.status_code == 201:
        return dict(r.json())
    else:
        MyUtils.logging_error(str(json.dumps(r.json())), debug)
        r.raise_for_status()


def process_request(request, real_resources, database_resources):
    global host_info_cache
    host = request["host"]
    structure_name = request["structure"]
    resource = request["resource"]
    current_value_label = {"cpu": "cpu_allowance_limit", "mem": "mem_limit"}

    # Apply the request and get the new resources to set
    new_resources = apply_request(request, real_resources, database_resources)

    if new_resources:
        MyUtils.logging_info("Request: " + request["action"] + " for container : " + request[
            "structure"] + " for new resources : " + json.dumps(new_resources), debug)

        try:
            # Get the previous values in case the scaling is not successfully and fully applied
            # previous_resource_limit = real_resources[resource]["current"]

            # Apply changes through a REST call
            applied_resources = set_container_resources(structure_name, host, new_resources)

            # Get the applied value
            current_value = applied_resources[resource][current_value_label[resource]]

            # Update the limits
            limits = db_handler.get_limits({"name": structure_name})
            limits["resources"][resource]["upper"] += request["amount"]
            limits["resources"][resource]["lower"] += request["amount"]
            db_handler.update_limit(limits)

            # Update the structure current value
            structure = db_handler.get_structure(structure_name)
            updated_structure = MyUtils.copy_structure_base(structure)
            updated_structure["resources"][resource] = dict()
            updated_structure["resources"][resource]["current"] = current_value
            MyUtils.update_structure(updated_structure, db_handler, debug=False, max_tries=2)

        except Exception as e:
            MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug)
            return
    else:
        raise Exception()


def rescale_container(request, structure_name):
    try:
        # Retrieve host info and cache it in case other containers or applications need it
        if request["host"] not in host_info_cache:
            host_info_cache[request["host"]] = db_handler.get_structure(request["host"])

        # Get the resources the container is using from its host NodeScaler (the 'current' value)
        real_resources = MyUtils.get_container_resources(structure_name)

        # Get the resources reported in the database (the 'max, min' values)
        database_resources = db_handler.get_structure(structure_name)

        # Process the request
        process_request(request, real_resources, database_resources)
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug)


def sort_containers_by_usage_margin(container1, container2, resource):
    # Return the container with the lowest margin between resources used and resources set (closest bottelneck)
    if MyUtils.get_resource(container1, resource)["current"] - MyUtils.get_resource(container1, resource)["usage"] < \
            MyUtils.get_resource(container2, resource)["current"] - MyUtils.get_resource(container2, resource)["usage"]:
        lowest, highest = container1, container2
    else:
        lowest, highest = container2, container1

    return lowest, highest


def lowest_current_to_usage_margin(container1, container2, resource):
    # Return the container with the lowest margin between resources used and resources set (closest bottelneck)
    lowest, _ = sort_containers_by_usage_margin(container1, container2, resource)
    return lowest


def highest_current_to_usage_margin(container1, container2, resource):
    # Return the container with the highest margin between resources used and resources set (lowest use)
    _, highest = sort_containers_by_usage_margin(container1, container2, resource)
    return highest


def generate_requests(new_requests, app_label):
    for req in new_requests:
        db_handler.add_request(req)
    rescaled_containers = [c["structure"] for c in new_requests]
    MyUtils.logging_info("App " + app_label + " rescaled by rescaling containers:  " + str(
        rescaled_containers) + " rescaling at " + MyUtils.get_time_now_string(), debug)


def single_container_rescale(request, app_containers):
    amount, resource = request["amount"], request["resource"]
    scalable_containers = list()
    resource_shares = abs(amount)
    for container in app_containers:
        metrics_to_retrieve = BDWATCHDOG_CONTAINER_METRICS[resource]
        usages = bdwatchdog_handler.get_structure_usages({"host": container["name"]}, 10, 20,
                                                         metrics_to_retrieve, RESCALER_CONTAINER_METRICS)
        MyUtils.get_resource(container, resource)["usage"] = usages[resource]
        if amount < 0:
            # Check that the container has enough free resource shares available to be released and that it would be able
            # to be rescaled without dropping under the minimum value
            if MyUtils.get_resource(container, resource)["current"] < resource_shares:
                # Container doesn't have enough resources to free
                pass
            elif MyUtils.get_resource(container, resource)["current"] + amount < container["resources"][resource][
                "min"]:
                # Container can't free that amount without dropping under the minimum
                pass
            else:
                scalable_containers.append(container)
        else:
            # Check that the container has enough free resource shares available in the host and that it would be able
            # to be rescaled without exceeded the maximum value
            container_host = container["host"]

            if host_info_cache[container_host]["resources"][resource]["free"] < resource_shares:
                # Container's host doesn't have enough free resources
                pass
            elif MyUtils.get_resource(container, resource)["current"] + amount > container["resources"][resource][
                "max"]:
                # Container can't get that amount without exceeding the maximum
                pass
            else:
                scalable_containers.append(container)

    # Look for the best fit container for this resource and launch the rescaling request for it
    if scalable_containers:
        best_fit_container = scalable_containers[0]

        for container in scalable_containers[1:]:
            if amount < 0:
                best_fit_container = highest_current_to_usage_margin(container, best_fit_container, resource)
            else:
                best_fit_container = lowest_current_to_usage_margin(container, best_fit_container, resource)

        new_request = dict(
            type="request",
            resource=resource,
            amount=amount,
            host=best_fit_container["host"],
            structure=best_fit_container["name"],
            action=MyUtils.generate_request_name(amount, resource),
            timestamp=int(time.time()))
        generate_requests([new_request], request["structure"])
        MyUtils.get_resource(best_fit_container, resource)["current"] += amount
        return True, best_fit_container
    else:
        return False, {}


def rescale_application(request, structure_name):
    # Get container names that this app uses
    app_containers_names = db_handler.get_structure(structure_name)["containers"]
    app_containers = list()

    for cont_name in app_containers_names:
        # Get the container
        container = db_handler.get_structure(cont_name)
        app_containers.append(container)

        # Retrieve host info and cache it in case other containers or applications need it
        if container["host"] not in host_info_cache:
            host_info_cache[container["host"]] = db_handler.get_structure(container["host"])

    # First try to fill the request by scaling just one container
    success, container_to_rescale = single_container_rescale(request, app_containers)

    # If unsuccessful, try to do it by multiple, smaller, rescaling operations
    if not success:
        total_amount = request["amount"]
        splits = int(3)
        smaller_amount = int(total_amount / splits)
        request["amount"] = smaller_amount
        success, iterations = True, 0
        while success and iterations < splits:
            iterations += 1
            success, container_to_rescale = single_container_rescale(request, app_containers)
            for c in app_containers:
                if c["name"] == container_to_rescale["name"]:
                    app_containers.remove(c)
                    app_containers.append(container_to_rescale)
    else:
        pass


def process_requests(reqs):
    for request in reqs:
        structure_name = request["structure"]

        # Retrieve structure info
        structure = db_handler.get_structure(structure_name)

        # Rescale the structure accordingly, whether it is a container or an application
        rescaling_function[structure["subtype"]](request, structure_name)

        # Remove the request from the database
        db_handler.delete_request(request)


def split_requests(all_requests):
    scale_down, scale_up = list(), list()
    for request in all_requests:
        if "action" not in request or not request["action"]:
            continue
        elif request["action"].endswith("Down"):
            scale_down.append(request)
        elif request["action"].endswith("Up"):
            scale_up.append(request)
    return scale_down, scale_up


def persist_new_host_information():
    global host_info_cache
    for host in host_info_cache:
        data = host_info_cache[host]
        success, tries, max_tries = False, 0, 10
        while not success:
            try:
                db_handler.update_structure(data)
                success = True
                print("Structure : " + data["subtype"] + " -> " + data["name"] + " updated at time: "
                      + time.strftime("%D %H:%M:%S", time.localtime()))
            except requests.exceptions.HTTPError:
                # Update failed because collision, still, keep trying
                tries += 1
                if tries >= max_tries:
                    raise


rescaling_function = {"container": rescale_container, "application": rescale_application}
apply_request_by_resource = {"cpu": apply_cpu_request, "mem": apply_mem_request}


def scale():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
    global debug
    global host_info_cache

    # Remove previous requests
    MyUtils.logging_info("Purging previous requests at " + MyUtils.get_time_now_string(), debug)
    filter_requests(0)

    while True:

        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # Heartbeat
        MyUtils.beat(db_handler, SERVICE_NAME)

        # CONFIG
        config = service["config"]
        polling_frequency = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
        request_timeout = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "REQUEST_TIMEOUT")
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")

        # Get the requests
        new_requests = filter_requests(request_timeout)
        if new_requests:
            MyUtils.logging_info("Requests at " + MyUtils.get_time_now_string(), debug)

            # Reset the cache
            host_info_cache = dict()

            # Split the requests between scale down and scale up
            scale_down, scale_up = split_requests(new_requests)

            # Process first the requests that free resources, then the one that use them
            process_requests(scale_down)
            process_requests(scale_up)

            # Persist the new host information
            persist_new_host_information()
        else:
            # No requests to process
            MyUtils.logging_info("No requests at " + MyUtils.get_time_now_string(), debug)

        time.sleep(polling_frequency)


def main():
    try:
        scale()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()
