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


def filter_requests(request_timeout):
    filtered_requests = list()
    merged_requests = list()
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
        if structure in structure_requests_dict and action in structure_requests_dict[structure]:
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
            if structure not in structure_requests_dict:
                structure_requests_dict[structure] = dict()
            structure_requests_dict[structure][action] = request

    for structure in structure_requests_dict:
        for action in structure_requests_dict[structure]:
            merged_requests.append(structure_requests_dict[structure][action])

    return merged_requests


def apply_request(request, resources, specified_resources):
    amount = request["amount"]
    resource_dict = dict()
    resource_dict[request["resource"]] = dict()

    if request["resource"] == "cpu":
        resource_dict["cpu"] = dict()
        current_cpu_limit = resources["cpu"]["cpu_allowance_limit"]
        if current_cpu_limit == "-1":
            # CPU is set to unlimited so just apply limit
            current_cpu_limit = specified_resources["max"]  # Start with max resources
            # current_cpu_limit = specified_resources["min"] # Start with min resources
            # Careful as values over the max and under the min can be generated with this code
        else:
            try:
                current_cpu_limit = int(current_cpu_limit)
            except ValueError:
                # Bad value
                return None

        effective_cpu_limit = int(resources["cpu"]["effective_num_cpus"])
        cpu_allowance_limit = current_cpu_limit + amount

        if cpu_allowance_limit + 100 < effective_cpu_limit or cpu_allowance_limit >= effective_cpu_limit:
            # Round up the number of cores needed as
            # - at least one core can be reclaimed because of underuse or
            # - not enough cores to apply the limit or close to the limit
            number_of_cpus_requested = int(math.ceil(cpu_allowance_limit / 100.0))

            # TODO Implement cpu resource management

            cpus_map = {"node0": ["0","2"],"node1":["1","3"],"node2":["4","6"],"node3":["5","7"]}
            #resource_dict["cpu"]["cpu_num"] = cpus_map[request["structure"]][0:number_of_cpus_requested]

            resource_dict["cpu"]["cpu_num"] = \
                str(cpus_map[request["structure"]][0]) + "," + \
                str(cpus_map[request["structure"]][number_of_cpus_requested-1])

            # resource_dict["cpu"]["cpu_num"] = \
            #     str(range(number_of_cpus_requested)[0]) + "-" + \
            #     str(range(number_of_cpus_requested)[-1])


        resource_dict["cpu"]["cpu_allowance_limit"] = cpu_allowance_limit

    elif request["resource"] == "mem":
        current_mem_limit = resources["mem"]["mem_limit"]
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

        if int(amount + current_mem_limit) < 0:
            raise ValueError("Error in setting memory, it is lower than 0")

        resource_dict["mem"] = dict()
        resource_dict["mem"]["mem_limit"] = str(int(amount + current_mem_limit))

    return resource_dict


def set_container_resources(container, host, resources):
    node_rescaler_endpoint = host
    r = requests.put("http://"+node_rescaler_endpoint+":8000/container/" + container, data=json.dumps(resources),
                     headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    if r.status_code == 201:
        return dict(r.json())
    else:
        print(json.dumps(r.json()))
        r.raise_for_status()


def process_request(request, real_resources, specified_resources):
    # Generate the changed_resources document
    new_resources = apply_request(request, real_resources, specified_resources)
    current_value_label = {"cpu": "cpu_allowance_limit", "mem": "mem_limit"}

    if new_resources:
        MyUtils.logging_info("Request: " + request["action"] + " for container : " + request[
            "structure"] + " for new resources : " + json.dumps(new_resources), debug)

        applied_resources = dict()
        try:
            structure_name = request["structure"]
            resource = request["resource"]
            host = request["host"]

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
            updated_structure = db_handler.get_structure(structure_name)
            updated_structure["resources"][resource]["current"] = current_value
            db_handler.update_structure(updated_structure)

        except requests.exceptions.HTTPError as e:
            MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug)
            return
        except KeyError as e:
            MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug)
            MyUtils.logging_error(json.dumps(applied_resources), debug)
            return
        except Exception as e:
            MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug)
            return

def rescale_container(request, structure_name):
    real_resources = MyUtils.get_container_resources(structure_name)
    specified_resources = db_handler.get_structure(structure_name)
    try:
        process_request(request, real_resources, specified_resources)
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug)


def rescale_application(request, structure_name):
    pass

def is_application(structure):
    return structure["subtype"] == "application"


def is_container(structure):
    return structure["subtype"] == "container"

def scale():
    logging.basicConfig(filename=SERVICE_NAME+'.log', level=logging.INFO)
    global debug
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
            for request in new_requests:
                structure_name = request["structure"]
                structure = db_handler.get_structure(structure_name)
                if is_application(structure):
                    rescale_application(request, structure_name)
                else:
                    rescale_container(request, structure_name)

        time.sleep(polling_frequency)


try:
    scale()
except Exception as e:
    MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug)
