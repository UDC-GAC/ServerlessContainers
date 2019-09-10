import random
import unittest
import time

import src.StateDatabase
from test.documents.rules import cpu_exceeded_upper, cpu_dropped_lower, mem_exceeded_upper, mem_dropped_lower, \
    CpuRescaleUp, energy_exceeded_upper, CpuRescaleDown, MemRescaleUp, MemRescaleDown, EnergyRescaleUp, \
    EnergyRescaleDown, energy_dropped_lower
from test.documents.services import guardian_service as guardian
from src.Guardian.Guardian import CPU_SHARES_PER_WATT, NOT_AVAILABLE_STRING
from src.MyUtils import MyUtils
from src.MyUtils.MyUtils import generate_event_name
from unittest import TestCase
from src.Guardian import Guardian
from src.StateDatabase.couchdb import CouchDBServer
from src.StateDatabase.opentsdb import OpenTSDBServer


class GuardianTest(TestCase):
    def setUp(self):
        self.guardian = Guardian.Guardian()

    def test_check_invalid_values(self):

        # An error should be thrown
        with self.assertRaises(ValueError):
            self.guardian.check_invalid_values(20, "label1", 10, "label2")

        # Nothing should happen
        TestCase.assertEqual(self, first=None, second=self.guardian.check_invalid_values(10, "label1", 20, "label2"))

    def test_check_unset_values(self):
        # An error should be thrown
        with self.assertRaises(ValueError):
            self.guardian.check_unset_values(NOT_AVAILABLE_STRING, "min", "cpu")

            # Nothing should happen
            self.guardian.check_unset_values(1, "min", "cpu")

    def test_try_get_value(self):
        TestCase.assertEqual(self, first=1, second=self.guardian.try_get_value({"KEY": 1}, "KEY"))
        TestCase.assertEqual(self, first=NOT_AVAILABLE_STRING,
                             second=self.guardian.try_get_value({"KEY": 1}, "NOKEY"))

    def test_generate_event_name(self):
        scale_down = {"scale": {"down": 5}}
        scale_up = {"scale": {"up": 2}}

        TestCase.assertEqual(self, first="CpuUnderuse", second=generate_event_name(scale_down, "cpu"))
        TestCase.assertEqual(self, first="MemUnderuse", second=generate_event_name(scale_down, "mem"))
        TestCase.assertEqual(self, first="DiskUnderuse", second=generate_event_name(scale_down, "disk"))
        TestCase.assertEqual(self, first="NetUnderuse", second=generate_event_name(scale_down, "net"))

        TestCase.assertEqual(self, first="CpuBottleneck", second=generate_event_name(scale_up, "cpu"))
        TestCase.assertEqual(self, first="MemBottleneck", second=generate_event_name(scale_up, "mem"))
        TestCase.assertEqual(self, first="DiskBottleneck", second=generate_event_name(scale_up, "disk"))
        TestCase.assertEqual(self, first="NetBottleneck", second=generate_event_name(scale_up, "net"))

        scale_invalid1 = {"bogus": 1}
        scale_invalid2 = {"scale": {"bogus": 1}}

        with self.assertRaises(ValueError):
            generate_event_name(scale_invalid1, "cpu")

        with self.assertRaises(ValueError):
            generate_event_name(scale_invalid2, "cpu")

    def test_filter_old_events(self):
        all_events = list()
        timeout = 20

        for i in range(0, 5):
            now = time.time()
            ago = now - timeout - 4
            all_events.append({"timestamp": now})
            all_events.append({"timestamp": ago})

        valid, invalid = self.guardian.sort_events(all_events, timeout)

        TestCase.assertEqual(self, first=5, second=len(invalid))
        TestCase.assertEqual(self, first=5, second=len(valid))

    def test_reduce_structure_events(self):
        input_events = list()
        for i in range(1, 5):
            input_events.append({"resource": "cpu", "action": {"events": {"scale": {"up": i, "down": 0}}}})

        for i in range(2, 6):
            input_events.append({"resource": "cpu", "action": {"events": {"scale": {"up": 0, "down": i}}}})

        expected_output = {"cpu": {"events": {"scale": {"up": sum(range(1, 5)), "down": sum(range(2, 6))}}}}

        TestCase.assertEqual(self, first=expected_output, second=self.guardian.reduce_structure_events(input_events))

    def test_correct_container_state(self):
        def get_valid_state():
            resources_dict = dict(
                cpu=dict(max=300, current=170, min=50),
                mem=dict(max=8192, current=4096, min=256)
            )

            limits_dict = dict(
                cpu=dict(upper=140, lower=110, boundary=30),
                mem=dict(upper=3072, lower=2048, boundary=1024)

            )
            return resources_dict, limits_dict

        # State should be valid
        resources, limits = get_valid_state()
        TestCase.assertEqual(self, first=limits, second=self.guardian.adjust_container_state(resources, limits, ["cpu","mem"]))

        # Make resources and limits invalid because invalid boundary
        for resource in ["cpu", "mem"]:
            resources, limits = get_valid_state()
            # Upper too close to current
            limits[resource]["upper"] = resources[resource]["current"] - int(limits[resource]["boundary"] / 2)
            TestCase.assertEqual(self, first=limits, second=self.guardian.adjust_container_state(resources, limits, ["cpu","mem"]))

            # Upper too far away to current
            limits[resource]["upper"] = resources[resource]["current"] - limits[resource]["boundary"] * 2
            TestCase.assertEqual(self, first=limits, second=self.guardian.adjust_container_state(resources, limits, ["cpu","mem"]))

            # Lower too close to upper
            limits[resource]["lower"] = limits[resource]["upper"] - int(limits[resource]["boundary"] / 2)
            TestCase.assertEqual(self, first=limits, second=self.guardian.adjust_container_state(resources, limits, ["cpu","mem"]))

            # Lower too far away to upper
            limits[resource]["lower"] = limits[resource]["upper"] - limits[resource]["boundary"] * 2
            TestCase.assertEqual(self, first=limits, second=self.guardian.adjust_container_state(resources, limits, ["cpu","mem"]))

    def test_invalid_container_state(self):
        def get_valid_state():
            resources_dict = dict(
                cpu=dict(max=300, current=170, min=50),
                mem=dict(max=8192, current=4096, min=256)
            )

            limits_dict = dict(
                cpu=dict(upper=140, lower=110, boundary=30),
                mem=dict(upper=3072, lower=2048, boundary=1024)

            )
            return resources_dict, limits_dict

        # State should be valid
        resources, limits = get_valid_state()
        for resource in ["cpu", "mem"]:
            self.assertFalse(self.guardian.check_invalid_container_state(resources, limits, resource))

        # Make resources and limits invalid because unset
        for resource in ["cpu", "mem"]:
            for key in [("max", "resource"), ("min", "resource"), ("upper", "limit"), ("lower", "limit")]:
                label, doc_type = key
                resources, limits = get_valid_state()
                if doc_type == "limit":
                    limits[resource][label] = NOT_AVAILABLE_STRING
                if doc_type == "resource":
                    resources[resource][label] = NOT_AVAILABLE_STRING
                with self.assertRaises(ValueError):
                    self.guardian.check_invalid_container_state(resources, limits, resource)

        for resource in ["cpu", "mem"]:
            # Invalid because max < current
            resources, limits = get_valid_state()
            resources[resource]["max"], resources[resource]["current"] = \
                resources[resource]["current"], resources[resource]["max"]
            with self.assertRaises(ValueError):
                self.guardian.check_invalid_container_state(resources, limits, resource)

            # Invalid because current < upper
            resources, limits = get_valid_state()
            resources[resource]["current"], limits[resource]["upper"] = \
                limits[resource]["upper"], resources[resource]["current"]
            with self.assertRaises(ValueError):
                self.guardian.check_invalid_container_state(resources, limits, resource)

            # Invalid because upper < lower
            resources, limits = get_valid_state()
            limits[resource]["upper"], limits[resource]["lower"] = limits[resource]["lower"], limits[resource]["upper"]
            with self.assertRaises(ValueError):
                self.guardian.check_invalid_container_state(resources, limits, resource)

            # Invalid because lower < min
            # TODO Test deactivated, see TODO in tested function
            # resources, limits = get_valid_state()
            # resources[resource]["min"], limits[resource]["lower"] = \
            #     limits[resource]["lower"], resources[resource]["min"]
            # with self.assertRaises(ValueError):
            #     self.guardian.check_invalid_container_state(resources, limits, resource)

        # Make resources and limits invalid because invalid boundary
        for resource in ["cpu", "mem"]:
            resources, limits = get_valid_state()
            # Upper too close to current
            limits[resource]["upper"] = resources[resource]["current"] - int(limits[resource]["boundary"] / 2)
            with self.assertRaises(ValueError):
                self.guardian.check_invalid_container_state(resources, limits, resource)
            # Upper too far away to current
            limits[resource]["upper"] = resources[resource]["current"] - limits[resource]["boundary"] * 2
            with self.assertRaises(ValueError):
                self.guardian.check_invalid_container_state(resources, limits, resource)

            # resources, limits = get_valid_state()
            # # Lower too close to upper
            # limits[resource]["lower"] = limits[resource]["upper"] - limits[resource]["boundary"] / 2
            # with self.assertRaises(ValueError):
            #     guardian.invalid_container_state(resources, limits)
            # # Lower too far away to upper
            # limits[resource]["lower"] = limits[resource]["upper"] - limits[resource]["boundary"] * 2
            # with self.assertRaises(ValueError):
            #     guardian.invalid_container_state(resources, limits)

    def test_get_container_resources_str(self):

        resources_dict = dict(
            cpu=dict(max=300, current=200, min=50),
            mem=dict(max=8192, current=2048, min=256),
            disk=dict(max=200, current=80, min=50),
            net=dict(max=200, current=80, min=50)
        )

        limits_dict = dict(
            cpu=dict(upper=140, lower=70, boundary=70),
            mem=dict(upper=8000, lower=7000, boundary=1000),
            disk=dict(upper=70, lower=60),
            net=dict(upper=70, lower=60)
        )

        usages_dict = {
            "structure.cpu.usage": 22.5664364,
            "structure.mem.usage": 2341.9734,
        }

        TestCase.assertEqual(self, first="300,200,140,22.57,70,50",
                             second=self.guardian.get_resource_summary("cpu", resources_dict, limits_dict,
                                                                       usages_dict))
        TestCase.assertEqual(self, first="8192,2048,8000,2341.97,7000,256",
                             second=self.guardian.get_resource_summary("mem", resources_dict, limits_dict,
                                                                       usages_dict))

    def test_container_energy_str(self):
        resources_dict = dict(
            energy=dict(max=50, usage=20, min=0)
        )

        TestCase.assertEqual(self, first="50,20,0", second=self.guardian.get_container_energy_str(resources_dict))

    def test_adjust_if_invalid_amount(self):
        structure_resources = {"max": 400, "min": 50, "current": 200}
        structure_limits = {"upper": 150, "lower": 100}

        # Correct cases
        TestCase.assertEqual(self, first=70,
                             second=self.guardian.adjust_amount(70, structure_resources, structure_limits))
        TestCase.assertEqual(self, first=100,
                             second=self.guardian.adjust_amount(100, structure_resources, structure_limits))

        # Over the max
        TestCase.assertEqual(self, first=200,
                             second=self.guardian.adjust_amount(250, structure_resources, structure_limits))
        TestCase.assertEqual(self, first=200,
                             second=self.guardian.adjust_amount(260, structure_resources, structure_limits))

        # Correct cases
        TestCase.assertEqual(self, first=-10,
                             second=self.guardian.adjust_amount(-10, structure_resources, structure_limits))
        TestCase.assertEqual(self, first=-50,
                             second=self.guardian.adjust_amount(-50, structure_resources, structure_limits))

        # Under the minimum
        TestCase.assertEqual(self, first=-50,
                             second=self.guardian.adjust_amount(-60, structure_resources, structure_limits))
        TestCase.assertEqual(self, first=-50,
                             second=self.guardian.adjust_amount(-100, structure_resources, structure_limits))

        structure_resources = {"max": 40, "min": 5, "current": 20}
        structure_limits = {"upper": 15, "lower": 10}
        TestCase.assertEqual(self, first=10,
                             second=self.guardian.adjust_amount(10, structure_resources, structure_limits))

    def test_get_amount_from_percentage_reduction(self):
        resource = "mem"
        structure = {"resources": {"mem": {"max": 4096, "min": 280, "current": 2000}}}
        usages = {"structure.mem.usage": 700}

        TestCase.assertEqual(self, first=-260,
                             second=self.guardian.get_amount_from_percentage_reduction(structure, usages, resource, 20))
        TestCase.assertEqual(self, first=-520,
                             second=self.guardian.get_amount_from_percentage_reduction(structure, usages, resource, 40))

        TestCase.assertEqual(self, first=-650,
                             second=self.guardian.get_amount_from_percentage_reduction(structure, usages, resource, 50))

        # Should max out at 50%
        TestCase.assertEqual(self, first=-650,
                             second=self.guardian.get_amount_from_percentage_reduction(structure, usages, resource, 70))

    def test_get_amount_from_proportional_energy_rescaling(self):
        resource = "energy"

        def check():
            data = structure["resources"]["energy"]
            expected = (data["max"] - data["usage"]) * CPU_SHARES_PER_WATT
            TestCase.assertEqual(self, first=expected,
                                 second=self.guardian.get_amount_from_proportional_energy_rescaling(structure,
                                                                                                    resource))

        structure = {"resources": {"energy": {"max": 60, "min": 10, "usage": 30}}}
        check()
        structure = {"resources": {"energy": {"max": 60, "min": 10, "usage": 80}}}
        check()

    def test_get_amount_from_fit_reduction(self):
        current_resource_limit = 2000
        current_resource_usage = 700
        boundary = 500

        # To properly fit the limit, the usage (700) has to be placed between the upper and lower limit,
        # keeping the inter-limit boundary (500) so the new limits should be (950,450)
        # finally, keeping the real resource limit to the upper limit boundary (500), the final
        # current value to apply should be (upper limit)950 + 500(boundary) = 1450
        # so the amount to reduce is 2000 - 1450 = 550
        TestCase.assertEqual(self,
                             first=self.guardian.get_amount_from_fit_reduction(current_resource_limit, boundary,
                                                                               current_resource_usage),
                             second=-550)

    def test_match_usages_and_limits(self):
        def assert_event_equals(rule, ev):
            event_expected_name = generate_event_name(rule["action"]["events"], rule["resource"])
            self.assertTrue(event_expected_name, ev["name"])
            self.assertTrue(structure_name, ev["structure"])
            self.assertTrue(rule["action"], ev["action"])
            self.assertTrue("event", ev["type"])
            self.assertTrue(rule["resource"], ev["resource"])

        mem_exceeded_upper["active"] = True
        mem_dropped_lower["active"] = True

        rules = [mem_exceeded_upper, mem_dropped_lower]
        structure_name = "node99"

        resources = dict(
            mem=dict(max=8192, current=4096, min=256, guard=True),
        )

        limits = dict(
            mem=dict(upper=2048, lower=1024),
        )
        usages = {"structure.mem.usage": 1536}

        # No events expected
        TestCase.assertEqual(self, [],
                             second=self.guardian.match_usages_and_limits(structure_name, rules, usages, limits,
                                                                          resources))

        # Expect mem underuse event
        usages["structure.mem.usage"] = limits["mem"]["lower"] - 100
        events = self.guardian.match_usages_and_limits(structure_name, rules, usages, limits, resources)
        if not events:
            self.fail("No events were triggered when expected.")
        else:
            event = events[0]
            assert_event_equals(mem_dropped_lower, event)

        # Expect mem bottleneck event
        usages["structure.mem.usage"] = limits["mem"]["upper"] + 100
        events = self.guardian.match_usages_and_limits(structure_name, rules, usages, limits, resources)
        if not events:
            self.fail("No events were triggered when expected.")
        else:
            event = events[0]
            assert_event_equals(mem_dropped_lower, event)

    def test_match_rules_and_events(self):

        def get_valid_state():
            st = {
                "guard": True,
                "guard_policy": "serverless",
                "host": "c14-13",
                "host_rescaler_ip": "c14-13",
                "host_rescaler_port": "8000",
                "name": "node0",
                "resources": {
                    "cpu": {
                        "current": 140,
                        "guard": True,
                        "max": 200,
                        "min": 50
                    },
                    "energy": {
                        "guard": False,
                        "max": 20,
                        "min": 0,
                        "usage": 2.34
                    },
                    "mem": {
                        "current": 3072,
                        "guard": True,
                        "max": 10240,
                        "min": 512
                    }
                },
                "subtype": "container",
                "type": "structure"
            }
            lim = {"cpu": {"upper": 120, "lower": 80, "boundary": 20},
                   "mem": {"upper": 2048, "lower": 1024, "boundary": 1024},
                   "energy": {"upper": 20, "lower": 10, "boundary": 5},
                   }

            us = {"structure.cpu.usage": 100, "structure.mem.usage": 1536, "structure.energy.usage": 15}

            return st, lim, us

        event_rules = [cpu_exceeded_upper, cpu_dropped_lower, mem_exceeded_upper, mem_dropped_lower,
                       energy_exceeded_upper, energy_dropped_lower]
        rescaling_rules = [CpuRescaleUp, CpuRescaleDown, MemRescaleUp, MemRescaleDown, EnergyRescaleUp,
                           EnergyRescaleDown]
        for rule in event_rules + rescaling_rules:
            rule["active"] = True

        for tuple in [("cpu", CpuRescaleDown, -50), ("mem", MemRescaleDown, -50), ("cpu", CpuRescaleUp, 100),
                      ("mem", MemRescaleUp, 2034)]:

            resource, rescale_rule, amount = tuple
            structure, limits, usages = get_valid_state()

            usages["structure." + resource + ".usage"] = limits[resource]["lower"] + amount
            events = list()

            num_needed_events = rescale_rule["rule"]["and"][0][">="][1]

            for i in range(num_needed_events):
                events += self.guardian.match_usages_and_limits(structure["name"], event_rules, usages, limits,
                                                                structure["resources"])
            events = self.guardian.reduce_structure_events(events)

            generated_requests, events_to_remove = self.guardian.match_rules_and_events(structure, rescaling_rules,
                                                                                        events, limits,
                                                                                        usages)

            expected_events_to_remove = dict()
            event_to_remove_name = MyUtils.generate_event_name(events[resource]["events"], resource)
            expected_events_to_remove[event_to_remove_name] = num_needed_events

            TestCase.assertEqual(self, first=expected_events_to_remove, second=events_to_remove)


class GuardianServelerssIntegrationTest(TestCase):

    def tearDown(self):
        self.couchdb.remove_database("services-test")
        self.couchdb.remove_database("structures-test")
        self.couchdb.remove_database("limits-test")
        self.couchdb.remove_database("rules-test")
        self.couchdb.remove_database("events-test")
        self.couchdb.remove_database("requests-test")
        self.couchdb.close_connection()
        self.opentsdb.close_connection()

    def setUp(self):
        def initialize_database(database_type, database_name):
            self.couchdb.set_database_name(database_type, database_name)
            if self.couchdb.database_exists(database_name):
                self.couchdb.remove_database(database_name)
            self.couchdb.create_database(database_name)

        self.couchdb = CouchDBServer("localhost", "5984")
        self.opentsdb = OpenTSDBServer("localhost", "4242")

        initialize_database("services", "services-test")
        initialize_database("structures", "structures-test")
        initialize_database("limits", "limits-test")
        initialize_database("rules", "rules-test")
        initialize_database("events", "events-test")
        initialize_database("requests", "requests-test")

        self.guardian = Guardian.Guardian()
        self.guardian.debug = False

        self.guardian.couchdb_handler = self.couchdb
        self.guardian.opentsdb_handler = self.opentsdb

    def test_serverless(self):
        guardian_service = guardian
        testing_node_name = "testingNode{0}".format(str(random.randint(0, 10)))
        structure = {"guard": True, "guard_policy": "serverless", "host": "c14-13", "host_rescaler_ip": "c14-13",
                     "host_rescaler_port": "8000",
                     "resources": {
                         "cpu": {
                             "current": 140,
                             "guard": True,
                             "max": 200,
                             "min": 50
                         },
                         "energy": {
                             "guard": True,
                             "max": 20,
                             "min": 0,
                             "usage": 2.34
                         },
                         "mem": {
                             "current": 3072,
                             "guard": True,
                             "max": 10240,
                             "min": 512
                         }
                     }, "subtype": "container", "type": "structure", "name": testing_node_name}

        limits = {"type": "limit", "resources": {"cpu": {"upper": 120, "lower": 80, "boundary": 20},
                                                 "mem": {"upper": 2048, "lower": 1024, "boundary": 1024},
                                                 "energy": {"upper": 20, "lower": 10, "boundary": 10}
                                                 }, "name": testing_node_name}

        event_rules = [cpu_exceeded_upper, cpu_dropped_lower, mem_exceeded_upper, mem_dropped_lower]
        rescaling_rules = [CpuRescaleUp, CpuRescaleDown, MemRescaleUp, MemRescaleDown]
        for rule in event_rules + rescaling_rules:
            rule["active"] = True

        guardian_service["config"]["WINDOW_TIMELAPSE"] = 20
        guardian_service["config"]["WINDOW_DELAY"] = 100 + random.randint(0, 100)
        guardian_service["config"]["EVENT_TIMEOUT"] = 100

        # Add the guardian service, a structure
        self.couchdb.add_service(guardian_service)
        guardian_service = self.couchdb.get_service("guardian")
        self.couchdb.add_structure(structure)

        # Check that without usage data, nothing is donde
        structure["guard"] = True
        self.guardian.serverless(self.couchdb.get_service("guardian")["config"], structure, self.couchdb.get_rules())
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_events(structure)))
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_requests(structure)))

        # Check that without limits, nothing is done
        structure["guard"] = True
        self.guardian.serverless(self.couchdb.get_service("guardian")["config"], structure, self.couchdb.get_rules())
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_events(structure)))
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_requests(structure)))

        # Add the limits and rules
        self.couchdb.add_limit(limits)
        for rule in event_rules + rescaling_rules:
            self.couchdb.add_rule(rule)

        time.sleep(2)  # Let the documents be persisted

        # Unguard the structure and check that nothing happens
        del (structure["guard"])
        self.guardian.serverless(self.couchdb.get_service("guardian")["config"], structure, self.couchdb.get_rules())
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_events(structure)))
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_requests(structure)))
        structure["guard"] = False
        self.guardian.serverless(self.couchdb.get_service("guardian")["config"], structure, self.couchdb.get_rules())
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_events(structure)))
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_requests(structure)))
        structure["guard"] = True

        # Inject some fake usage data for the structure
        # User cpu is LOWER than the upper limit -> nothing happens
        base_cpu_doc = {"timestamp": 0, "metric": "proc.cpu.user", "value": 0, "tags": {"host": testing_node_name}}
        time_seconds_ago = time.time() - (
                guardian_service["config"]["WINDOW_TIMELAPSE"] + guardian_service["config"]["WINDOW_DELAY"])
        fake_docs = list()
        usage = limits["resources"]["cpu"]["lower"]
        for i in range(guardian_service["config"]["WINDOW_TIMELAPSE"]):
            doc = dict(base_cpu_doc)
            doc["timestamp"] = time_seconds_ago + i
            doc["value"] = usage + i
            fake_docs.append(doc)
        success, error = self.opentsdb.send_json_documents(fake_docs)
        self.assertTrue(success)

        time.sleep(2)  # Let the time series database persist the new metrics

        # CPU usage is normal so nothing should happen
        self.guardian.serverless(self.couchdb.get_service("guardian")["config"], structure, self.couchdb.get_rules())
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_events(structure)))
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_requests(structure)))

        # Move the guardian back in time
        guardian_service["config"]["WINDOW_DELAY"] += 50
        self.couchdb.update_service(guardian_service)

        # User cpu is HIGHER than the upper limit -> 1 cpu bottleneck event should be generated
        base_cpu_doc = {"timestamp": 0, "metric": "proc.cpu.user", "value": 0, "tags": {"host": testing_node_name}}
        time_seconds_ago = time.time() - (
                guardian_service["config"]["WINDOW_TIMELAPSE"] + guardian_service["config"]["WINDOW_DELAY"]) - 5
        fake_docs = list()
        usage = limits["resources"]["cpu"]["upper"]
        for i in range(guardian_service["config"]["WINDOW_TIMELAPSE"] + 5):
            doc = dict(base_cpu_doc)
            doc["timestamp"] = time_seconds_ago + i
            doc["value"] = usage + i
            fake_docs.append(doc)
        success, error = self.opentsdb.send_json_documents(fake_docs)
        self.assertTrue(success)
        time.sleep(2)  # Let the time series database persist the new metrics
        self.guardian.serverless(self.couchdb.get_service("guardian")["config"], structure, self.couchdb.get_rules())
        time.sleep(1)  # Let the documents be persisted
        events = self.couchdb.get_events(structure)
        TestCase.assertEqual(self, first=1, second=len(events))
        TestCase.assertEqual(self, first="CpuBottleneck", second=events[0]["name"])
        TestCase.assertEqual(self, first=0, second=len(self.couchdb.get_requests(structure)))
        self.couchdb.delete_num_events_by_structure(structure, "CpuBottleneck", 1)

        # Move the guardian back in time
        guardian_service["config"]["WINDOW_DELAY"] += 200
        self.couchdb.update_service(guardian_service)

        # Simulate the generation of a request for cpu and memory by making the guardian go through all the time windows
        num_needed_events = CpuRescaleUp["rule"]["and"][0][">="][1]
        for i in range(num_needed_events):
            fake_docs = list()
            usage = limits["resources"]["cpu"]["upper"]
            time_seconds_ago = time.time() - (
                    guardian_service["config"]["WINDOW_TIMELAPSE"] + guardian_service["config"]["WINDOW_DELAY"])
            for j in range(guardian_service["config"]["WINDOW_TIMELAPSE"]):
                doc = dict(base_cpu_doc)
                doc["timestamp"] = time_seconds_ago + j
                doc["value"] = usage + j
                fake_docs.append(doc)
            success, error = self.opentsdb.send_json_documents(fake_docs)
            self.assertTrue(success)
            time.sleep(1)  # Let the time series database persist the new metrics
            self.guardian.serverless(self.couchdb.get_service("guardian")["config"], structure,
                                     self.couchdb.get_rules())
            # time.sleep(1)  # Let the documents be persisted
            if i + 1 < num_needed_events:
                events = self.couchdb.get_events(structure)
                TestCase.assertEqual(self, first=i + 1, second=len(events))

            # Move the guardian forward in time
            guardian_service["config"]["WINDOW_DELAY"] -= guardian_service["config"]["WINDOW_TIMELAPSE"]
            self.couchdb.update_service(guardian_service)

        # The majority of events should have been removed when the request was generated
        events = self.couchdb.get_events(structure)
        # TestCase.assertTrue(self, len(events) < num_needed_events)
        TestCase.assertEqual(self, first=0, second=len(events))

        # 1 requests should have been generated
        requests = self.couchdb.get_requests(structure)
        TestCase.assertEqual(self, first=1, second=len(requests))
        TestCase.assertEqual(self, first="CpuRescaleUp", second=requests[0]["action"])


if __name__ == '__main__':
    unittest.main()
