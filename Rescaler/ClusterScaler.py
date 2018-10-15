# /usr/bin/python
from __future__ import print_function

import StateDatabase.couchDB as couchDB
import MyUtils.MyUtils as MyUtils
import json
import time
import requests
import traceback
import logging
import StateDatabase.bdwatchdog as bdwatchdog

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "REQUEST_TIMEOUT": 60, "DEBUG": True}
SERVICE_NAME = "scaler"
db_handler = couchDB.CouchDBServer()
rescaler_http_session = requests.Session()
bdwatchdog_handler = bdwatchdog.BDWatchdog()
debug = True

BDWATCHDOG_CONTAINER_METRICS = {"cpu": ['proc.cpu.user', 'proc.cpu.kernel'],
                                "mem": ['proc.mem.resident'],
                                "disk": ['proc.disk.writes.mb', 'proc.disk.reads.mb'],
                                "net": ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb']}
RESCALER_CONTAINER_METRICS = {'cpu': ['proc.cpu.user', 'proc.cpu.kernel'], 'mem': ['proc.mem.resident'],
                              'disk': ['proc.disk.writes.mb', 'proc.disk.reads.mb'],
                              'net': ['proc.net.tcp.in.mb', 'proc.net.tcp.out.mb']}

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
        for action in structure_requests_dict[structure]:
            final_requests.append(structure_requests_dict[structure][action])

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
    structure_name = request["structure"]
    host_info = host_info_cache[request["host"]]

    core_usage_map = host_info["resources"][resource]["core_usage_mapping"]

    # Check the container's core mapping and correct it is necessary
    # current_cpu_limit = get_current_resource_value(database_resources, real_resources, resource)
    # cpu_list = MyUtils.get_cpu_list(real_resources["cpu"]["cpu_num"])
    # current_cpu_limit, used_cores = check_container_cpu_mapping(structure_name, request, core_usage_map, cpu_list,
    #                                                            current_cpu_limit)

    current_cpu_limit = get_current_resource_value(database_resources, real_resources, resource)
    cpu_list = MyUtils.get_cpu_list(real_resources["cpu"]["cpu_num"])

    host_max_cores = int(host_info["resources"]["cpu"]["max"] / 100)
    host_cpu_list = [str(i) for i in range(host_max_cores)]
    for core in host_cpu_list:
        if core not in core_usage_map:
            core_usage_map[core] = dict()
            core_usage_map[core]["free"] = 100
        if structure_name not in core_usage_map[core]:
            core_usage_map[core][structure_name] = 0

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
    if any(core in used_cores for core in ["12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23"]):
        raise ValueError("ERROR, setting wrong cpus")

    resource_dict = {resource: {}}
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
    resource_dict = {request["resource"]: {}}
    current_disk_limit = get_current_resource_value(database_resources, real_resources, request["resource"])

    # Return the dictionary to set the resources
    resource_dict["disk"]["disk_read_limit"] = str(int(amount + current_disk_limit))
    resource_dict["disk"]["disk_write_limit"] = str(int(amount + current_disk_limit))

    return resource_dict


def apply_net_request(request, database_resources, real_resources, amount):
    resource_dict = {request["resource"]: {}}
    current_net_limit = get_current_resource_value(database_resources, real_resources, request["resource"])

    # Return the dictionary to set the resources
    resource_dict["net"]["net_limit"] = str(int(amount + current_net_limit))

    return resource_dict


def check_invalid_resource_value(database_resources, amount, value, resource):
    max_resource_limit = int(database_resources["resources"][resource]["max"])
    min_resource_limit = int(database_resources["resources"][resource]["min"])
    resource_limit = int(value + amount)
    if resource_limit < 0:
        raise ValueError("Error in setting {0}, it would be lower than 0".format(resource))
    elif resource_limit < min_resource_limit:
        raise ValueError("Error in setting {0}, it would be lower than min".format(resource))
    elif resource_limit > max_resource_limit:
        raise ValueError("Error in setting {0}, it would be higher than max".format(resource))


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
            raise ValueError("Bad current {0} limit value".format(resource))
    return current_resource_limit


def check_host_has_enough_free_resources(host_info, needed_resources, resource):
    if host_info["resources"][resource]["free"] < needed_resources:
        raise ValueError("Error in setting {0}, couldn't get the resources needed".format(resource))


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


def set_container_resources(container, node_rescaler_endpoint, node_rescaler_port, resources, rescaler_http_session):
    r = rescaler_http_session.put(
        "http://{0}:{1}/container/{2}".format(node_rescaler_endpoint, node_rescaler_port, container),
        data=json.dumps(resources),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    if r.status_code == 201:
        return dict(r.json())
    else:
        MyUtils.logging_error(str(json.dumps(r.json())), debug)
        r.raise_for_status()


def process_request(request, real_resources, database_resources):
    global host_info_cache
    rescaler_ip = request["host_rescaler_ip"]
    rescaler_port = request["host_rescaler_port"]
    structure_name = request["structure"]
    resource = request["resource"]
    current_value_label = {"cpu": "cpu_allowance_limit", "mem": "mem_limit", "disk": "disk_read_limit",
                           "net": "net_limit"}

    # Apply the request and get the new resources to set
    new_resources = apply_request(request, real_resources, database_resources)

    if new_resources:
        MyUtils.logging_info("Request: {0} for container : {1} for new resources : {2}".format(
            request["action"], request["structure"], json.dumps(new_resources)), debug)

        try:
            # Get the previous values in case the scaling is not successfully and fully applied
            # previous_resource_limit = real_resources[resource]["current"]

            # Apply changes through a REST call
            applied_resources = set_container_resources(structure_name, rescaler_ip, rescaler_port, new_resources,
                                                        rescaler_http_session)

            # Get the applied value
            current_value = applied_resources[resource][current_value_label[resource]]

            # Update the limits
            # limits = db_handler.get_limits({"name": structure_name})
            # limits["resources"][resource]["upper"] += request["amount"]
            # limits["resources"][resource]["lower"] += request["amount"]
            # db_handler.update_limit(limits)

            # Update the structure current value but with a low priority (2 tries)
            # structure = db_handler.get_structure(structure_name)
            # updated_structure = MyUtils.copy_structure_base(structure)
            # updated_structure["resources"][resource] = dict()
            # updated_structure["resources"][resource]["current"] = current_value
            # MyUtils.update_structure(updated_structure, db_handler, debug=False, max_tries=2)

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

        # Needed for the resources reported in the database (the 'max, min' values)
        database_resources = db_handler.get_structure(structure_name)

        # Get the resources the container is using from its host NodeScaler (the 'current' value)
        container = database_resources
        real_resources = MyUtils.get_container_resources(container, rescaler_http_session, debug)
        if not real_resources:
            MyUtils.logging_error("Couldn't get container's {0} resources, can't rescale".format(structure_name), debug)
            return

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
    MyUtils.logging_info("App {0} rescaled by rescaling containers: {1} rescaling at {2}".format(
        app_label, str(rescaled_containers), MyUtils.get_time_now_string()), debug)


def single_container_rescale(request, app_containers):
    amount, resource = request["amount"], request["resource"]
    scalable_containers = list()
    resource_shares = abs(amount)
    for container in app_containers:
        metrics_to_retrieve = BDWATCHDOG_CONTAINER_METRICS[resource]
        usages = bdwatchdog_handler.get_structure_timeseries({"host": container["name"]}, 10, 20,
                                                             metrics_to_retrieve, RESCALER_CONTAINER_METRICS)
        MyUtils.get_resource(container, resource)["usage"] = usages[resource]
        if amount < 0:
            # Check that the container has enough free resource shares
            # available to be released and that it would be able
            # to be rescaled without dropping under the minimum value
            if MyUtils.get_resource(container, resource)["current"] < resource_shares:
                # Container doesn't have enough resources to free
                pass
            elif MyUtils.get_resource(container, resource)["current"] + amount < \
                    container["resources"][resource]["min"]:
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
            elif MyUtils.get_resource(container, resource)["current"] + \
                    amount > container["resources"][resource]["max"]:
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
            # if "for_energy" in request and request["for_energy"]:
            #     if amount < 0:
            #         best_fit_container = lowest_current_to_usage_margin(container, best_fit_container, resource)
            #     else:
            #         best_fit_container = highest_current_to_usage_margin(container, best_fit_container, resource)
            # else:
            #     if amount < 0:
            #         best_fit_container = highest_current_to_usage_margin(container, best_fit_container, resource)
            #     else:
            #         best_fit_container = lowest_current_to_usage_margin(container, best_fit_container, resource)

        # Generate the new request
        new_request = dict(
            type="request",
            resource=resource,
            amount=amount,
            host=best_fit_container["host"],
            host_rescaler_ip=best_fit_container["host_rescaler_ip"],
            host_rescaler_port=best_fit_container["host_rescaler_port"],
            structure=best_fit_container["name"],
            action=MyUtils.generate_request_name(amount, resource),
            timestamp=int(time.time()))

        # generate_requests([new_request], request["structure"])

        # Update the containers resources
        # MyUtils.get_resource(best_fit_container, resource)["current"] += amount

        return True, best_fit_container, new_request
    else:
        return False, {}, {}


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
    # success, container_to_rescale = single_container_rescale(request, app_containers)

    # If unsuccessful, try to do it by multiple, smaller, rescaling operations
    # if not success:

    total_amount = request["amount"]

    if total_amount == 0:
        MyUtils.logging_info("Empty request at".format(MyUtils.get_time_now_string()), debug)
        return
    splits = abs(total_amount / 12)  # len(app_containers)

    if splits == 0:
        splits = 1

    # Can't have more splits than containers as if two splits fall on the same container,
    # only one will be applied due to the 'latest rescaling only' policy
    smaller_amount = int(total_amount / splits)
    request["amount"] = smaller_amount
    success, iterations = True, 0
    generated_requests = dict()
    while success and iterations < splits:
        success, container_to_rescale, generated_request = single_container_rescale(request, app_containers)
        if not success:
            break
        else:
            # If rescaling was successful, update the container's resources as they have been rescaled
            for c in app_containers:
                container_name = c["name"]
                if container_name == container_to_rescale["name"]:
                    if container_name not in generated_requests:
                        generated_requests[container_name] = list()

                    generated_requests[container_name].append(generated_request)
                    MyUtils.get_resource(container_to_rescale, request["resource"])["current"] += request["amount"]
                    app_containers.remove(c)
                    app_containers.append(container_to_rescale)
                    break

        iterations += 1

    for c in generated_requests:
        final_request = dict(generated_requests[c][0])
        final_request["amount"] = 0
        for request in generated_requests[c][0:]:
            final_request["amount"] += request["amount"]
        generate_requests([final_request], request["structure"])

    if iterations < splits:
        # Couldn't completely rescale the application as some split of a major rescaling operation could
        # not be completed
        MyUtils.logging_warning(
            "App {0} could not be completely rescaled, only: {1} shares of resource: {2} have been rescaled".format(
                request["structure"], str(iterations * smaller_amount), request["resource"]), debug)


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
                MyUtils.update_structure(data, db_handler, debug)
                success = True
                MyUtils.logging_info("Structure : {0} -> {1} updated at time: {2}".format(
                    data["subtype"], data["name"], time.strftime("%D %H:%M:%S", time.localtime())), debug)
            except requests.exceptions.HTTPError:
                # Update failed because collision, still, keep trying
                tries += 1
                if tries >= max_tries:
                    raise


rescaling_function = {"container": rescale_container, "application": rescale_application}
apply_request_by_resource = {"cpu": apply_cpu_request, "mem": apply_mem_request, "disk": apply_disk_request,
                             "net": apply_net_request}


def scale():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
    global debug
    global host_info_cache

    # Remove previous requests
    MyUtils.logging_info("Purging previous requests at {0}".format(MyUtils.get_time_now_string()), debug)
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
            MyUtils.logging_info("Requests at {0}".format(MyUtils.get_time_now_string()), debug)

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
            MyUtils.logging_info("No requests at {0}".format(MyUtils.get_time_now_string()), debug)

        time.sleep(polling_frequency)


def main():
    MAX_RELOADS = 2
    load = 0
    while load <= MAX_RELOADS:
        try:
            # This functions acts like an infinite loop and should never return aside from an exception
            scale()
        except Exception as e:
            MyUtils.logging_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)
        load += 1
        MyUtils.logging_error("Reloading {0} for the {1} time out of {2}".format(SERVICE_NAME, load, MAX_RELOADS),
                              debug=True)


if __name__ == "__main__":
    main()
