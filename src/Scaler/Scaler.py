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

import time
import requests
import traceback
from copy import deepcopy
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor

import src.MyUtils.MyUtils as utils
import src.StateDatabase.opentsdb as bdwatchdog
from src.Scaler.ContainerScaler import ContainerScaler
from src.Scaler.ApplicationScaler import ApplicationScaler
from src.Scaler.UserScaler import UserScaler
from src.Scaler.DataLoader import DataLoader
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service


CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "REQUEST_TIMEOUT": 60, "CHECK_CORE_MAP": True, "ACTIVE": True, "DEBUG": True}


class Scaler(Service):
    """ Scaler class that implements the logic for this microservice. """

    def __init__(self):
        super().__init__("scaler", ConfigValidator(min_frequency=3), CONFIG_DEFAULT_VALUES, sleep_attr="polling_frequency")
        self.rescaler_session = requests.Session()
        self.bdwatchdog_handler = bdwatchdog.OpenTSDBServer()
        self.host_info_cache, self.host_changes, self.container_info_cache = {}, {}, {}

        self.polling_frequency, self.request_timeout, self.check_core_map, self.active, self.debug = None, None, None, None, None

        self.execution_context, self.data_context, self.original_data = None, None, None
        self.container_scaler, self.application_scaler, self.user_scaler = None, None, None
        self.data_loader, self.last_request_retrieval = None, None

    @staticmethod
    def _split_requests_by_type(requests):
        user_reqs = [r for r in requests if r["structure_type"] == "user"]
        app_reqs = [r for r in requests if r["structure_type"] == "application"]
        cont_reqs = [r for r in requests if r["structure_type"] == "container"]
        return user_reqs, app_reqs, cont_reqs

    def _print_header(self, header):
        self.log_info("=" * 80)
        self.log_info(header)
        self.log_info("=" * 80)

    def _print_time(self, msg, start_time, end_time):
        self.log_info("{0} in {1:.2f} seconds".format(msg, end_time - start_time))
        self.log_info("." * 80)

    def _reset_env(self):
        self.execution_context, self.data_context, self.original_data = None, None, None
        self.container_scaler, self.application_scaler, self.user_scaler = None, None, None

    def _filter_requests(self, request_timeout):
        fresh_requests, purged_requests, final_requests = [], [], []
        purged_counter = 0
        duplicated_counter = 0

        # Remote database operation
        all_requests = self.couchdb_handler.get_requests()
        self.last_request_retrieval = time.time()

        # First purge the old requests
        for request in all_requests:
            if request["timestamp"] < self.last_request_retrieval - request_timeout:
                purged_requests.append(request)
                purged_counter += 1
            else:
                fresh_requests.append(request)

        # Then remove repeated requests for the same structure if found
        structure_requests_dict = {}
        for request in fresh_requests:
            structure_name = request["structure"]  # The structure name (string), acting as an id
            action = request["action"]  # The action name (string)
            field = request["field"]  # Structure field that will be modified (i.e., "current" or "max")
            action_field = "{0}_{1}".format(action, field)  # Used as a unique identifier
            stored_request = structure_requests_dict.get(structure_name, {}).get(action_field,  None)
            if stored_request:
                # A previous request was found for this structure, remove old one and leave the newer one
                if "priority" in stored_request and "priority" in request and stored_request["priority"] != request["priority"]:
                    # First, try comparing priorities
                    higher_priority_request = stored_request if stored_request["priority"] > request["priority"] else request
                else:
                    # If no priorities available, compare timestamps (newer requests are prioritised)
                    higher_priority_request = stored_request if stored_request["timestamp"] > request["timestamp"] else request

                if higher_priority_request is stored_request:
                    # The stored request has a higher priority or is newer, leave it and mark the retrieved one to be removed
                    purged_requests.append(request)
                else:
                    # The stored request has a lower priority or is older, mark it to be removed and save the retrieved one
                    purged_requests.append(stored_request)
                    structure_requests_dict[structure_name][action_field] = request

                duplicated_counter += 1
            else:
                structure_requests_dict[structure_name] = {action_field: request}

        self.couchdb_handler.delete_requests(purged_requests)

        for structure in structure_requests_dict:
            for action_field in structure_requests_dict[structure]:
                final_requests.append(structure_requests_dict[structure][action_field])

        self.log_info("Number of purged/duplicated requests was {0}/{1}".format(purged_counter, duplicated_counter))
        return final_requests

    def _process_requests(self, _requests, method, op, host_changes, host_locks, max_tries=1):
        removed, failed, tries = False, [], 0
        while _requests and tries < max_tries:
            tries += 1
            futures = []
            with ThreadPoolExecutor() as executor:
                for req in _requests:
                    kwargs = {}
                    if req.get_type() == "container":
                        lock = host_locks.setdefault(req.host, Lock())
                        kwargs = {"host_changes": host_changes, "host_lock": lock}

                    fn = getattr(req, method)
                    futures.append((executor.submit(fn, self.original_data, **kwargs), req))

            failed = []
            for future, req in futures:
                success = future.result()
                if success:
                    if method == "execute":
                        op.mark_request_executed(req)
                    else:
                        op.remove_request_executed(req)
                else:
                    self.log_warning("Request {0} has failed: {1}".format(method, req))
                    failed.append(req)
            _requests = failed

        return failed

    def _remove_requests(self, _requests):
        threads = []
        for req in _requests:
            # Ensure the request has been persisted in database, otherwise there is no need to remove it
            if req["timestamp"] <= self.last_request_retrieval and req.get("_id", ""):
                try:
                    # Remove the request from the database
                    thread = Thread(target=self.couchdb_handler.delete_request, args=(req,))
                    thread.start()
                    threads.append(thread)
                except Exception as e:
                    self.log_error(f"Failed to remove request {req}: {str(e)}")
                    continue

        for thread in threads:
            thread.join()

    def _persist_new_host_information(self, host_changes):
        def persist_thread(_host, _changes, _handler, _debug):
            utils.partial_update_structure(_host, _changes, _handler, _debug)
        threads = []
        for hostname in self.original_data.hosts:
            if hostname in host_changes:
                host = self.original_data.hosts[hostname]
                t = Thread(target=persist_thread, args=(host, host_changes[hostname], self.couchdb_handler, self.debug))
                t.start()
                threads.append(t)
            else:
                self.log_info("Host {0} has not been modified, skipping persist".format(hostname))

        for t in threads:
            t.join()

    def planning_phase(self, user_reqs, app_reqs, cont_reqs):
        user_operations, app_operations, cont_operations = [], [], []
        t0 = time.time()

        # 1) Plan user requests execution and generate user operations
        if user_reqs:
            self.log_info("--- Processing {0} user requests ---".format(len(user_reqs)))
            user_operations = self.user_scaler.plan(user_reqs)
            self.log_info("--- Generated {0} user operations ---".format(len(user_operations)))

        # 2) Plan application requests execution and generate application operations
        if app_reqs:
            self.log_info("--- Processing {0} application requests ---".format(len(app_reqs)))
            app_operations = self.application_scaler.plan(app_reqs)
            self.log_info("--- Generated {0} application operations ---".format(len(app_operations)))

        # 3) Plan container requests execution and generate container operations
        if cont_reqs:
            self.log_info("--- Processing {0} container requests ---".format(len(cont_reqs)))
            cont_operations = self.container_scaler.plan(cont_reqs)
            self.log_info("--- Generated {0} container operations ---".format(len(cont_operations)))

        t1 = time.time()
        self._print_time("Planning phase completed", t0, t1)

        return user_operations, app_operations, cont_operations

    def execution_phase(self, user_operations, app_operations, cont_operations):
        host_changes, host_locks = {}, {}
        t0 = time.time()

        # Operation requests are executed in bottom-top order: Container -> Application -> User
        for op in user_operations + app_operations + cont_operations:
            # Print operation info
            self.log_info(op)

            # Process container requests
            failed = self._process_requests(op.container_requests, method="execute", op=op,
                                            host_changes=host_changes, host_locks=host_locks)

            # Process application and user requests only if all container requests have succeeded
            if not failed:
                failed += self._process_requests(op.application_requests + op.user_requests, method="execute",
                                                 op=op, host_changes=None, host_locks=None)

            # If some request has failed, rollback the full operation
            if failed:
                # Rollback application and user requests
                self._process_requests(reversed(op.application_executed_requests + op.user_executed_requests),
                                       method="rollback", op=op, host_changes=None, host_locks=None, max_tries=3)

                # Rollback container requests
                self._process_requests(reversed(op.container_executed_requests), method="rollback", op=op,
                                       host_changes=host_changes, host_locks=host_locks, max_tries=3)

        self._persist_new_host_information(host_changes)

        t1 = time.time()
        self._print_time("Execution phase completed", t0, t1)

    def scale_structures(self, new_requests):
        try:
            # Create a copy of data context for execution phase
            self.original_data = deepcopy(self.data_context)

            # Initialise scalers with data context
            self.container_scaler = ContainerScaler(self.couchdb_handler, self.rescaler_session, self.data_context, self.debug)
            self.application_scaler = ApplicationScaler(self.couchdb_handler, self.rescaler_session, self.data_context, self.debug)
            self.user_scaler = UserScaler(self.couchdb_handler, self.rescaler_session, self.data_context, self.debug)

            # 1) PLANNING PHASE
            self._print_header("PHASE 1: PLANNING")
            # Split requests by structure type (user, application, container)
            user_reqs, app_reqs, cont_reqs = self._split_requests_by_type(new_requests)
            # Create atomic operations based on current requests
            user_operations, app_operations, cont_operations = self.planning_phase(user_reqs, app_reqs, cont_reqs)

            # 2) EXECUTION PHASE
            self._print_header("PHASE 2: EXECUTION")
            # Execute atomic operations and rollback if some request fails
            self.execution_phase(user_operations, app_operations, cont_operations)
            # Remove requests from database
            self._remove_requests(new_requests)

        finally:
            # Clean context for next iteration
            self._reset_env()

    def on_start(self):
        self.log_info("Purging any previous requests")
        self._filter_requests(0)
        self.log_info("----------------------\n")

    def work(self,):
        thread = None
        try:
            # Get new requests
            new_requests = self._filter_requests(self.request_timeout)

            if not new_requests and not self.check_core_map:
                self.log_info("No requests to process and core map check is not enabled, skipping epoch")
                return thread

            t0 = time.time()

            # Initialise data loader
            self.data_loader = DataLoader(self.couchdb_handler, self.bdwatchdog_handler, self.rescaler_session, self.debug)

            # Load data
            self._print_header("LOADING DATA")
            if not self.data_loader.load_data(new_requests):
                self.log_error("Failed to load data, aborting all requests")
                return thread

            # Get data context
            self.data_context = self.data_loader.get_data_context()

            t1 = time.time()
            self._print_time("Data loaded", t0, t1)

            if self.check_core_map:
                self._print_header("CHECKING CORE MAP")
                # TODO: Add core map checking here

        except (Exception, RuntimeError) as e:
            self.log_error("Error loading data, skipping epoch altogether")
            self.log_error(str(e))
            return thread

        if not new_requests:
            self.log_info("No requests to process, skipping epoch")
            return thread

        thread = Thread(name="scale_structures", target=self.scale_structures, args=(new_requests,))
        thread.start()
        return thread

    def scale(self, ):
        self.run_loop()


def main():
    try:
        scaler = Scaler()
        scaler.scale()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()
