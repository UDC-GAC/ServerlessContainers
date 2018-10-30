import unittest
import time

from MyUtils import MyUtils
from MyUtils.MyUtils import generate_event_name
from unittest import TestCase
from Guardian.Guardian import adjust_if_invalid_amount, get_container_resources_str, check_invalid_values, \
    check_unset_values, NOT_AVAILABLE_STRING, try_get_value, reduce_structure_events, invalid_container_state, \
    get_container_energy_str, get_amount_from_percentage_reduction, get_amount_from_fit_reduction, \
    match_usages_and_limits, filter_old_events, correct_container_state, get_amount_from_proportional_energy_rescaling, \
    CPU_SHARES_PER_WATT, match_rules_and_events
from StateDatabase.initializers.rules import mem_exceeded_upper, mem_dropped_lower, MemRescaleUp, MemRescaleDown, \
    cpu_exceeded_upper, cpu_dropped_lower, energy_dropped_lower, energy_exceeded_upper, CpuRescaleUp, CpuRescaleDown, \
    EnergyRescaleDown, EnergyRescaleUp


class GuardianTest(TestCase):
    def test_check_invalid_values(self):

        # An error should be thrown
        with self.assertRaises(ValueError):
            check_invalid_values(20, "label1", 10, "label2")

        # Nothing should happen
        TestCase.assertEqual(self, first=None, second=check_invalid_values(10, "label1", 20, "label2"))

    def test_check_unset_values(self):
        # An error should be thrown
        with self.assertRaises(ValueError):
            check_unset_values(NOT_AVAILABLE_STRING, NOT_AVAILABLE_STRING)

        # Nothing should happen
        check_unset_values(1, NOT_AVAILABLE_STRING)

    def test_try_get_value(self):
        TestCase.assertEqual(self, first=1, second=try_get_value({"KEY": 1}, "KEY"))
        TestCase.assertEqual(self, first=NOT_AVAILABLE_STRING, second=try_get_value({"KEY": 1}, "NOKEY"))

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

        valid, invalid = filter_old_events(all_events, timeout)

        TestCase.assertEqual(self, first=5, second=len(invalid))
        TestCase.assertEqual(self, first=5, second=len(valid))

    def test_reduce_structure_events(self):
        input_events = list()
        for i in range(1, 5):
            input_events.append({"resource": "cpu", "action": {"events": {"scale": {"up": i, "down": 0}}}})

        for i in range(2, 6):
            input_events.append({"resource": "cpu", "action": {"events": {"scale": {"up": 0, "down": i}}}})

        expected_output = {"cpu": {"events": {"scale": {"up": sum(range(1, 5)), "down": sum(range(2, 6))}}}}

        TestCase.assertEqual(self, first=expected_output, second=reduce_structure_events(input_events))

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
        TestCase.assertEqual(self, first=limits, second=correct_container_state(resources, limits))

        # Make resources and limits invalid because invalid boundary
        for resource in ["cpu", "mem"]:
            resources, limits = get_valid_state()
            # Upper too close to current
            limits[resource]["upper"] = resources[resource]["current"] - limits[resource]["boundary"] / 2
            TestCase.assertEqual(self, first=limits, second=correct_container_state(resources, limits))

            # Upper too far away to current
            limits[resource]["upper"] = resources[resource]["current"] - limits[resource]["boundary"] * 2
            TestCase.assertEqual(self, first=limits, second=correct_container_state(resources, limits))

            # Lower too close to upper
            limits[resource]["lower"] = limits[resource]["upper"] - limits[resource]["boundary"] / 2
            TestCase.assertEqual(self, first=limits, second=correct_container_state(resources, limits))

            # Lower too far away to upper
            limits[resource]["lower"] = limits[resource]["upper"] - limits[resource]["boundary"] * 2
            TestCase.assertEqual(self, first=limits, second=correct_container_state(resources, limits))

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
        self.assertFalse(invalid_container_state(resources, limits))

        # Make resources and limits invalid because unset
        for resource in ["cpu", "mem"]:
            for key in [("max", "resource"), ("min", "resource"), ("upper", "limit"), ("lower", "limit")]:
                label, type = key
                resources, limits = get_valid_state()
                if type == "limit":
                    limits[resource][label] = NOT_AVAILABLE_STRING
                if type == "resource":
                    resources[resource][label] = NOT_AVAILABLE_STRING
                with self.assertRaises(ValueError):
                    invalid_container_state(resources, limits)

        for resource in ["cpu", "mem"]:
            # Invalid because max < current
            resources, limits = get_valid_state()
            resources[resource]["max"], resources[resource]["current"] = \
                resources[resource]["current"], resources[resource]["max"]
            with self.assertRaises(ValueError):
                invalid_container_state(resources, limits)

            # Invalid because current < upper
            resources, limits = get_valid_state()
            resources[resource]["current"], limits[resource]["upper"] = \
                limits[resource]["upper"], resources[resource]["current"]
            with self.assertRaises(ValueError):
                invalid_container_state(resources, limits)

            # Invalid because upper < lower
            resources, limits = get_valid_state()
            limits[resource]["upper"], limits[resource]["lower"] = limits[resource]["lower"], limits[resource]["upper"]
            with self.assertRaises(ValueError):
                invalid_container_state(resources, limits)

            # Invalid because lower < min
            resources, limits = get_valid_state()
            resources[resource]["min"], limits[resource]["lower"] = \
                limits[resource]["lower"], resources[resource]["min"]
            with self.assertRaises(ValueError):
                invalid_container_state(resources, limits)

        # Make resources and limits invalid because invalid boundary
        for resource in ["cpu", "mem"]:
            resources, limits = get_valid_state()
            # Upper too close to current
            limits[resource]["upper"] = resources[resource]["current"] - limits[resource]["boundary"] / 2
            with self.assertRaises(ValueError):
                invalid_container_state(resources, limits)
            # Upper too far away to current
            limits[resource]["upper"] = resources[resource]["current"] - limits[resource]["boundary"] * 2
            with self.assertRaises(ValueError):
                invalid_container_state(resources, limits)

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
                             second=get_container_resources_str("cpu", resources_dict, limits_dict, usages_dict))
        TestCase.assertEqual(self, first="8192,2048,8000,2341.97,7000,256",
                             second=get_container_resources_str("mem", resources_dict, limits_dict, usages_dict))

    def test_container_energy_str(self):
        resources_dict = dict(
            energy=dict(max=50, usage=20, min=0)
        )

        TestCase.assertEqual(self, first="50,20,0", second=get_container_energy_str(resources_dict))

    def test_adjust_if_invalid_amount(self):
        resource = "cpu"
        structure = {"resources": {"cpu": {"max": 400, "min": 50, "current": 200}}}
        limits = {"resources": {"cpu": {"upper": 150, "lower": 100}}}

        # Correct cases
        TestCase.assertEqual(self, first=70, second=adjust_if_invalid_amount(70, resource, structure, limits))
        TestCase.assertEqual(self, first=100, second=adjust_if_invalid_amount(100, resource, structure, limits))

        # Over the max
        TestCase.assertEqual(self, first=200, second=adjust_if_invalid_amount(250, resource, structure, limits))
        TestCase.assertEqual(self, first=200, second=adjust_if_invalid_amount(260, resource, structure, limits))

        # Correct cases
        TestCase.assertEqual(self, first=-10, second=adjust_if_invalid_amount(-10, resource, structure, limits))
        TestCase.assertEqual(self, first=-50, second=adjust_if_invalid_amount(-50, resource, structure, limits))

        # Under the minimum
        TestCase.assertEqual(self, first=-50, second=adjust_if_invalid_amount(-60, resource, structure, limits))
        TestCase.assertEqual(self, first=-50, second=adjust_if_invalid_amount(-100, resource, structure, limits))


        resource = "energy"
        structure = {"resources": {"energy": {"max": 40, "min": 5, "current": 20}}}
        limits = {"resources": {"energy": {"upper": 15, "lower": 10}}}
        TestCase.assertEqual(self, first=10, second=adjust_if_invalid_amount(10, resource, structure, limits))

    def test_get_amount_from_percentage_reduction(self):
        resource = "mem"
        structure = {"resources": {"mem": {"max": 4096, "min": 280, "current": 2000}}}
        usages = {"structure.mem.usage": 700}

        TestCase.assertEqual(self, first=-260,
                             second=get_amount_from_percentage_reduction(structure, usages, resource, 20))
        TestCase.assertEqual(self, first=-520,
                             second=get_amount_from_percentage_reduction(structure, usages, resource, 40))

        TestCase.assertEqual(self, first=-650,
                             second=get_amount_from_percentage_reduction(structure, usages, resource, 50))

        # Should max out at 50%
        TestCase.assertEqual(self, first=-650,
                             second=get_amount_from_percentage_reduction(structure, usages, resource, 70))

    def test_get_amount_from_proportional_energy_rescaling(self):
        resource = "energy"

        def check():
            data = structure["resources"]["energy"]
            expected = (data["max"] - data["usage"]) * CPU_SHARES_PER_WATT
            TestCase.assertEqual(self, first=expected,
                                 second=get_amount_from_proportional_energy_rescaling(structure, resource))

        structure = {"resources": {"energy": {"max": 60, "min": 10, "usage": 30}}}
        check()
        structure = {"resources": {"energy": {"max": 60, "min": 10, "usage": 80}}}
        check()

    def test_get_amount_from_fit_reduction(self):
        resource = "mem"
        structure = {"resources": {"mem": {"max": 4096, "min": 256, "current": 2000}}}
        usages = {"structure.mem.usage": 700}
        limits = {"resources": {"mem": {"upper": 1500, "lower": 1000, "boundary": 500}}}

        # To properly fit the limit, the usage (700) has to be placed between the upper and lower limit,
        # keeping the inter-limit boundary (500) so the new limits should be (950,450)
        # finally, keeping the real resource limit to the upper limit boundary (500), the final
        # current value to apply should be (upper limit)950 + 500(boundary) = 1450
        # so the amount to reduce is 2000 - 1450 = 550
        TestCase.assertEqual(self, first=get_amount_from_fit_reduction(structure, usages, resource, limits),
                             second=-550)

    def test_match_usages_and_limits(self):
        def assertEventEquals(rule, event):
            event_expected_name = generate_event_name(rule["action"]["events"], rule["resource"])
            self.assertTrue(event_expected_name, event["name"])
            self.assertTrue(structure_name, event["structure"])
            self.assertTrue(rule["action"], event["action"])
            self.assertTrue("event", event["type"])
            self.assertTrue(rule["resource"], event["resource"])

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
        TestCase.assertEqual(self, [], second=match_usages_and_limits(structure_name, rules, usages, limits, resources))

        # Expect mem underuse event
        usages["structure.mem.usage"] = limits["mem"]["lower"] - 100
        events = match_usages_and_limits(structure_name, rules, usages, limits, resources)
        if not events:
            self.fail("No events were triggered when expected.")
        else:
            event = events[0]
            assertEventEquals(mem_dropped_lower, event)

        # Expect mem bottleneck event
        usages["structure.mem.usage"] = limits["mem"]["upper"] + 100
        events = match_usages_and_limits(structure_name, rules, usages, limits, resources)
        if not events:
            self.fail("No events were triggered when expected.")
        else:
            event = events[0]
            assertEventEquals(mem_dropped_lower, event)

    def test_match_rules_and_events(self):

        def get_valid_state():
            structure = {
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
            limits = {"resources": {"cpu":
                                        {"upper": 120, "lower": 80, "boundary": 20},
                                    "mem":
                                        {"upper": 2048, "lower": 1024, "boundary": 1024},
                                    "energy":
                                        {"upper": 20, "lower": 10, "boundary": 5},
                                    }
                      }
            usages = {"structure.cpu.usage": 100, "structure.mem.usage": 1536, "structure.energy.usage": 15}

            return structure, limits, usages

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

            usages["structure." + resource + ".usage"] = limits["resources"][resource]["lower"] + amount
            events = list()

            num_needed_events = rescale_rule["rule"]["and"][0][">="][1]

            for i in range(num_needed_events):
                events += match_usages_and_limits(structure["name"], event_rules, usages, limits["resources"],
                                                  structure["resources"])
            events = reduce_structure_events(events)

            generated_requests, events_to_remove = match_rules_and_events(structure, rescaling_rules, events, limits,
                                                                          usages)

            expected_events_to_remove = dict()
            event_to_remove_name = MyUtils.generate_event_name(events[resource]["events"], resource)
            expected_events_to_remove[event_to_remove_name] = num_needed_events

            TestCase.assertEqual(self, first=expected_events_to_remove, second=events_to_remove)


if __name__ == '__main__':
    unittest.main()
