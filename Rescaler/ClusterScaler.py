# /usr/bin/python
from __future__ import print_function
import StateDatabase.couchDB as couchDB
import MyUtils.MyUtils as MyUtils
import json
import time
import requests
import math
import traceback
import logging

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "REQUEST_TIMEOUT": 600, "DEBUG": True}
SERVICE_NAME = "scaler"
db_handler = couchDB.CouchDBServer()
debug = True

host_info_cache = dict()

def filter_requests(request_timeout):
    filtered_requests = list()
    final_requests = list()
    all_requests = db_handler.get_requests()
    # First purge the old requests
    for request in all_requests:
        if request["timestamp"] < time.time() - request_timeout:
            db_handler.delete_request(request)
        else:
            filtered_requests.append(request)

    # Then remove repeated requests for the same structure if found
    structure_requests_dict = dict()
    for request in filtered_requests:
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


def apply_request(request, real_resources, database_resources, host_info_cache):
    amount = int(request["amount"])
    resource_dict = dict()
    resource_dict[request["resource"]] = dict()
    structure_name = request["structure"]

    if request["resource"] == "cpu":
        current_cpu_limit = real_resources["cpu"]["cpu_allowance_limit"]
        if current_cpu_limit == "-1":
            # CPU is set to unlimited so just apply limit
            current_cpu_limit = database_resources["resources"]["cpu"]["max"]  # Start with max resources
            # current_cpu_limit = specified_resources["min"] # Start with min resources
            # Careful as values over the max and under the min can be generated with this code
        else:
            try:
                current_cpu_limit = int(current_cpu_limit)
            except ValueError:
                # Bad value
                raise ValueError("Bad current cpu limit value")

        max_cpu_limit = int(database_resources["resources"]["cpu"]["max"])
        cpu_allowance_limit = int(current_cpu_limit + amount)

        # FIXME can't be 0 or over the max value
        if cpu_allowance_limit < 0:
            raise ValueError("Error in setting cpu, it is lower than 0")
        elif cpu_allowance_limit > max_cpu_limit:
            raise ValueError("Error in setting cpu, it would be higher than max")

        host_info = host_info_cache[request["host"]]

        core_usage_map = host_info["resources"]["cpu"]["core_usage_mapping"]

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

            # Check that the host has enough free shares
            if host_info["resources"]["cpu"]["free"] < needed_shares:
                raise ValueError("Error in setting cpu, couldn't get the resources needed")
                # FIXME couldn't do rescale down properly as shares to free remain

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
                else:
                    # This core is full
                    pass


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
                # FIXME couldn't do rescale down properly as shares to free remain
            else:
                # Update the free shares available in the host
                host_info["resources"]["cpu"]["free"] -= amount

        elif amount < 0:
            # Rescale down so free all shares and claim new one to see how many cores can be freed
            shares_to_free = int((-1) * amount)

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
                # FIXME couldn't do rescale down properly as shares to free remain
            else:
                # Update the free shares available in the host
                host_info["resources"]["cpu"]["free"] -= amount

        # No error thrown, so persist the new mapping to the cache
        host_info_cache[request["host"]]["resources"]["cpu"]["core_usage_mapping"] = core_usage_map
        host_info_cache[request["host"]]["resources"]["cpu"]["free"] = host_info["resources"]["cpu"]["free"]
        resource_dict["cpu"]["cpu_num"] = (",").join(used_cores)
        resource_dict["cpu"]["cpu_allowance_limit"] = cpu_allowance_limit

    elif request["resource"] == "mem":
        current_mem_limit = real_resources["mem"]["mem_limit"]
        if current_mem_limit == "-1":
            # MEM is set to unlimited so just apply limit
            # TODO Implement unlimited memory option policy
            return None
        else:
            try:
                current_mem_limit = int(current_mem_limit)
            except ValueError:
                # Bad value
                return None

        if amount > 0:
            free_host_memory = host_info_cache[request["host"]]["resources"]["mem"]["free"]
            if free_host_memory < amount:
                raise ValueError("Error in setting memory, not enough free memory")
        elif amount < 0:
            if int(amount + current_mem_limit) < 0:
                raise ValueError("Error in setting memory, it is lower than 0")


        host_info_cache[request["host"]]["resources"]["mem"]["free"] -= amount

        resource_dict["mem"] = dict()
        resource_dict["mem"]["mem_limit"] = str(int(amount + current_mem_limit))

    return resource_dict, host_info_cache


def set_container_resources(container, host, resources):
    node_rescaler_endpoint = host
    r = requests.put("http://" + node_rescaler_endpoint + ":8000/container/" + container, data=json.dumps(resources),
                     headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    if r.status_code == 201:
        return dict(r.json())
    else:
        print(json.dumps(r.json()))
        r.raise_for_status()


def process_request(request, real_resources, database_resources):
    # Generate the changed_resources document
    global host_info_cache
    host = request["host"]
    new_resources, host_info_cache = apply_request(request, real_resources, database_resources, host_info_cache)
    current_value_label = {"cpu": "cpu_allowance_limit", "mem": "mem_limit"}

    if new_resources:
        MyUtils.logging_info("Request: " + request["action"] + " for container : " + request[
            "structure"] + " for new resources : " + json.dumps(new_resources), debug)

        applied_resources = dict()
        try:
            structure_name = request["structure"]
            resource = request["resource"]

            # Get the previous values in case the scaling is not successfully and fully applied
            # previous_resource_limit = real_resources[resource]["current"]

            # Apply changes through a REST call
            applied_resources = set_container_resources(structure_name, host, new_resources)

            # Get the applied value
            current_value = applied_resources[resource][current_value_label[resource]]

            # Remove the request from the database
            db_handler.delete_request(request)

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


def rescale_container(request, structure_name):
    try:
        # Retrieve host info and cache it in case other containers need it
        if request["host"] not in host_info_cache:
            host_info_cache[request["host"]] = db_handler.get_structure(request["host"])

        real_resources = MyUtils.get_container_resources(structure_name)
        database_resources = db_handler.get_structure(structure_name)
        process_request(request, real_resources, database_resources)
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug)


def rescale_application(request, structure_name):
    pass


def is_application(structure):
    return structure["subtype"] == "application"


def is_container(structure):
    return structure["subtype"] == "container"


def process_requests(requests):
    for request in requests:
        # Retrieve structure info
        structure_name = request["structure"]
        structure = db_handler.get_structure(structure_name)

        if is_application(structure):
            rescale_application(request, structure_name)
        else:
            rescale_container(request, structure_name)

def scale():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
    global debug
    global host_info_cache

    # Remove previous requests
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

        new_requests = filter_requests(request_timeout)
        if not new_requests:
            # No requests to process
            MyUtils.logging_info("No requests at " + MyUtils.get_time_now_string(), debug)
        else:
            MyUtils.logging_info("Requests at " + MyUtils.get_time_now_string(), debug)

            # Reset the cache
            host_info_cache = dict()

            scale_down = list()
            scale_up = list()
            for request in new_requests:
                if request["action"].endswith("Down"):
                    scale_down.append(request)
                elif request["action"].endswith("Up"):
                    scale_up.append(request)

            # Process first the requests that free resources, then the one that use them
            process_requests(scale_down)
            process_requests(scale_up)

            for host in host_info_cache:
                data = host_info_cache[host]
                success = False
                while not success:
                    try:
                        db_handler.update_structure(data)
                        success = True
                        print("Structure : " + data["subtype"] + " -> " + data["name"] + " updated at time: "
                              + time.strftime("%D %H:%M:%S", time.localtime()))
                    except requests.exceptions.HTTPError as e:
                        pass

        time.sleep(polling_frequency)

def main():
    try:
        scale()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()