#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es)
#     - Roberto R. Expósito
#     - Juan Touriño
#
# This file is part of the ServerlessContainers framework, from
# now on referred to as ServerlessContainers.
#
# ServerlessContainers is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# ServerlessContainers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ServerlessContainers. If not, see <http://www.gnu.org/licenses/>.


from __future__ import print_function

from threading import Thread, Lock
import time
import traceback
import logging

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 5, "DEBUG": True, "STRUCTURE_GUARDED": "container",
                         "KP": 17.65, "KI": 11.93, "ANTI_WINDUP_METHOD": "clamping", "ACTIVE": True}

SERVICE_NAME = "pi_controller"


class PIController:

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.sum_error = {}
        self.host_info, self.host_info_lock = {}, Lock()
        self.u_min = 10  # Minimum CPU usage to avoid completely throttling applications
        self.window_timelapse, self.window_delay, self.anti_windup_method, self.debug = None, None, None, None
        self.structure_guarded, self.kp, self.ki, self.active = None, None, None, None

    def register_structure_values(self, host, structure_name, structure, power_error, cpu_usage, cpu_limit):
        scaling_type = "up" if power_error > 0 else "down"
        with self.host_info_lock:
            if host not in self.host_info:
                self.host_info[host] = {
                    "structures": {},
                    "global": {
                        "cpu": {
                            "usage": 0,
                            "min": 0,
                            "current": 0,
                            "max": 0,
                        },
                        "power": {"usage": 0},
                        "scalings": {
                            "up": 0,
                            "down": 0
                        }
                    },
                    "scalings": {
                        "up": {},
                        "down": {},
                    },
                    "cpu": {},
                }
            self.host_info[host]["structures"][structure_name] = structure
            self.host_info[host]["scalings"][scaling_type][structure_name] = power_error
            self.host_info[host]["global"]["scalings"][scaling_type] += power_error
            self.host_info[host]["cpu"][structure_name] = cpu_usage
            self.host_info[host]["global"]["cpu"]["usage"] += cpu_usage
            self.host_info[host]["global"]["cpu"]["min"] += cpu_limit["min"]
            self.host_info[host]["global"]["cpu"]["current"] += cpu_limit["current"]
            self.host_info[host]["global"]["cpu"]["max"] += cpu_limit["max"]

    def register_host_power(self, host, value):
        with self.host_info_lock:
            self.host_info[host]["global"]["power"]["usage"] = value

    def get_structure_info_thread(self, structure):
        try:
            # Remote database operation
            usages = utils.get_structure_usages(["cpu", "energy"], structure,
                                                self.window_timelapse, self.window_delay,
                                                self.opentsdb_handler, self.debug)

            if not usages:
                utils.log_error("No usage data for structure {0}. Skipping structure.".format(structure["name"]), self.debug)
                return

            container_power_budget = structure["resources"]["energy"]["max"]
            container_power_usage = usages[utils.res_to_metric("energy")]
            container_power_error = container_power_budget - container_power_usage
            container_cpu_usage = usages[utils.res_to_metric("cpu")]
            print(f"[{structure['name']}] Power budget is {container_power_budget}W and current consumption is {container_power_usage}W")
            print(f"[{structure['name']}] Needed scale is {container_power_error}W and CPU usage is {container_cpu_usage} shares")
            self.register_structure_values(structure["host"], structure["name"], structure, container_power_error,
                                           container_cpu_usage, structure["resources"]["cpu"])
        except Exception as e:
            utils.log_error("Error with structure {0}: {1}".format(structure["name"], str(e)), self.debug)

    def get_structure_info(self, structures):
        self.host_info = {}

        threads = []
        for structure in structures:
            thread = Thread(name="get_structure_info_{0}".format(structure["name"]), target=self.get_structure_info_thread,
                            args=(structure,))
            thread.start()
            threads.append(thread)

        for process in threads:
            process.join()

    def get_host_power_thread(self, host):
        rapl_structure = {"name": f"{host}-rapl", "subtype": "container"}
        # Remote database operation
        rapl_report = utils.get_structure_usages(["energy"], rapl_structure, self.window_timelapse,
                                                 self.window_delay, self.opentsdb_handler, self.debug)
        cpu_power_usage = rapl_report[utils.res_to_metric("energy")]

        # Register value
        self.register_host_power(host, cpu_power_usage)

    def get_host_power(self, hosts):
        threads = []
        for host in hosts:
            thread = Thread(name="get_host_power_{0}".format(host), target=self.get_host_power_thread, args=(host,))
            thread.start()
            threads.append(thread)

        for process in threads:
            process.join()

    def actuate(self, e_k, I_k, u_min, u_max):
        u_unsat = self.kp * e_k + self.ki * (I_k + e_k)
        u_sat = max(min(u_unsat, u_max), u_min)
        anti_wdup_gain = u_sat - u_unsat
        print(f"Kp ({self.kp}) * e(k) ({e_k}) + ki ({self.ki}) * I(k) ({I_k + e_k}) = {u_unsat} -> {u_sat} ")

        return u_sat, anti_wdup_gain

    def update_error(self, host, e_k, gain):
        if self.anti_windup_method == "clamping" and gain != 0:
            print(f"Anti-windup method is campling and anti-windup gain is {gain}. Error will not be updated.")
            return
        kaw = 1 / self.ki
        previous_error = self.sum_error[host]
        self.sum_error[host] += e_k + gain * kaw
        print(f"I(k) has been updated {previous_error} ---> {self.sum_error[host]}")

    def compute_global_scalings(self, hosts):
        generated_requests = []
        for host in hosts:
            global_cpu_scale = {}
            acum_error = self.sum_error.setdefault(host, 0)
            power_scale_up = self.host_info[host]["global"]["scalings"]["up"]
            power_scale_down = self.host_info[host]["global"]["scalings"]["down"]

            net_power_scale = power_scale_up + power_scale_down
            new_u, gain = self.actuate(net_power_scale, acum_error, self.host_info[host]["global"]["cpu"]["min"], self.host_info[host]["global"]["cpu"]["max"])
            net_cpu_scale = new_u - self.host_info[host]["global"]["cpu"]["current"]

            print(f"CPU needs a net power scale of {net_power_scale}W which means a CPU scale of {net_cpu_scale} shares")

            # Update I(k) taking into account anti-windup gain if needed (back-calculation)
            self.update_error(host, net_power_scale, gain)

            # Linearly interpolate global amount to scale up/down from net CPU scale
            global_cpu_scale["up"] = power_scale_up * (net_cpu_scale / net_power_scale)
            global_cpu_scale["down"] = power_scale_down * (net_cpu_scale / net_power_scale)

            # Distribute global CPU scale up/down among containers who requested to scale up/down proportionally
            for scale_type in global_cpu_scale:
                global_power_scale = self.host_info[host]["global"]["scalings"][scale_type]
                for cont_name, cont_power_scale in self.host_info[host]["scalings"][scale_type].items():
                    # Get structure info
                    structure = self.host_info[host]["structures"][cont_name]
                    # Compute proportional scaling for this structure
                    cont_cpu_scale = global_cpu_scale[scale_type] * (cont_power_scale / global_power_scale)
                    if cont_cpu_scale != 0:
                        # Generate and append request for this structure
                        request = utils.generate_request(structure, cont_cpu_scale, "energy")
                        generated_requests.append(request)

        return generated_requests

    def control_structures(self, structures):
        # Get the usage and power of all structures and register by host
        self.get_structure_info(structures)

        # Get the global host power using RAPL
        hosts = list(self.host_info.keys())
        self.get_host_power(hosts)

        # Compute the required CPU scaling for each container
        generated_requests = self.compute_global_scalings(hosts)

        # Send requests to remote database
        self.couchdb_handler.add_requests(generated_requests)

    def get_valid_structures(self, structures):
        validation_steps = [
            # Check structures have valid subtype
            (lambda s: utils.structure_subtype_is_supported(s["subtype"]), "All the structures have an unknown structure subtype"),
            # Get structures set to guard
            (lambda s: s.get("guard", False), "No structure set to guard, skipping"),
            # Get structures having 'energy' set to guard
            (lambda s: s.get("resources", {}).get("energy", {}).get("guard", False), "No structure has 'energy' set to guard, skipping"),
        ]
        valid_structures = structures
        if valid_structures:
            for cond, msg in validation_steps:
                valid_structures = [s for s in valid_structures if cond(s)]
                if not valid_structures:
                    utils.log_warning(msg, self.debug)
                    break
        return valid_structures

    def invalid_conf(self, ):
        if self.structure_guarded not in ["container", "application"]:
            return True, "Structure to be guarded '{0}' is invalid".format(self.structure_guarded)

        #for key, num in [("WINDOW_TIMELAPSE", self.window_timelapse), ("WINDOW_DELAY", self.window_delay), ("EVENT_TIMEOUT", self.event_timeout)]:
        #    if num < 5:
        #        return True, "Configuration item '{0}' with a value of '{1}' is likely invalid".format(key, num)
        return False, ""

    def control(self, ):
        myConfig = utils.MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO,
                            format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT)

        while True:

            #utils.update_service_config(self, SERVICE_NAME, myConfig, self.couchdb_handler)
            for key, value in myConfig.get_config().items():
                setattr(self, key.lower(), value)

            t0 = utils.start_epoch(self.debug)

            utils.print_service_config(self, myConfig, self.debug)

            ## CHECK INVALID CONFIG ##
            invalid, message = self.invalid_conf()
            if invalid:
                utils.log_error(message, self.debug)
                if self.window_timelapse < 5:
                    utils.log_error("Window difference is too short, replacing with DEFAULT value '{0}'".format(CONFIG_DEFAULT_VALUES["WINDOW_TIMELAPSE"]), self.debug)
                    self.window_timelapse = CONFIG_DEFAULT_VALUES["WINDOW_TIMELAPSE"]
                time.sleep(self.window_timelapse)
                utils.end_epoch(self.debug, self.window_timelapse, t0)
                continue

            thread = None
            if self.active:
                # Remote database operation
                structures = utils.get_structures(self.couchdb_handler, self.debug, subtype=self.structure_guarded)
                valid_structures = self.get_valid_structures(structures)
                if valid_structures:
                    utils.log_info("{0} Structures to process, launching threads".format(len(valid_structures)), self.debug)
                    thread = Thread(name="control_structures", target=self.control_structures, args=(valid_structures,))
                    thread.start()
                else:
                    utils.log_info("No valid structures to process", self.debug)
            else:
                utils.log_warning("PI Controller is not activated", self.debug)

            time.sleep(self.window_timelapse)

            utils.wait_operation_thread(thread, self.debug)

            utils.end_epoch(t0, self.window_timelapse, t0)


def main():
    try:
        pi_controller = PIController()
        pi_controller.control()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
