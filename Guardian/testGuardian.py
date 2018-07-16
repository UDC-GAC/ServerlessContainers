import unittest
import Guardian.Guardian as guardian
import time


class GuardianTest(unittest.TestCase):
    guardian = guardian

    def test_check_invalid_values(self):

        # An error should be thrown
        with self.assertRaises(ValueError):
            guardian.check_invalid_values(20, "label1", 10, "label2")

        # Nothing should happen
        self.assertEquals(None, guardian.check_invalid_values(10, "label1", 20, "label2"))

    def test_check_unset_values(self):
        # An error should be thrown
        with self.assertRaises(ValueError):
            guardian.check_unset_values(guardian.NOT_AVAILABLE_STRING, guardian.NOT_AVAILABLE_STRING)

        # Nothing should happen
        guardian.check_unset_values(1, guardian.NOT_AVAILABLE_STRING)

    def test_try_get_value(self):
        self.assertEquals(1, guardian.try_get_value({"KEY": 1}, "KEY"))
        self.assertEquals(guardian.NOT_AVAILABLE_STRING, guardian.try_get_value({"KEY": 1}, "NOKEY"))

    def test_generate_event_name(self):
        scale_down = {"scale": {"down": 5}}
        scale_up = {"scale": {"up": 2}}

        self.assertEquals("CpuUnderuse", guardian.generate_event_name(scale_down, "cpu"))
        self.assertEquals("MemUnderuse", guardian.generate_event_name(scale_down, "mem"))
        self.assertEquals("DiskUnderuse", guardian.generate_event_name(scale_down, "disk"))
        self.assertEquals("NetUnderuse", guardian.generate_event_name(scale_down, "net"))

        self.assertEquals("CpuBottleneck", guardian.generate_event_name(scale_up, "cpu"))
        self.assertEquals("MemBottleneck", guardian.generate_event_name(scale_up, "mem"))
        self.assertEquals("DiskBottleneck", guardian.generate_event_name(scale_up, "disk"))
        self.assertEquals("NetBottleneck", guardian.generate_event_name(scale_up, "net"))

        scale_invalid1 = {"bogus": 1}
        scale_invalid2 = {"scale": {"bogus": 1}}

        with self.assertRaises(ValueError):
            guardian.generate_event_name(scale_invalid1, "cpu")

        with self.assertRaises(ValueError):
            guardian.generate_event_name(scale_invalid2, "cpu")


    def test_filter_old_events(self):
        all_events = list()
        timeout = 20

        for i in range(0, 5):
            now = time.time()
            ago = now - timeout - 4
            all_events.append({"timestamp": now})
            all_events.append({"timestamp": ago})

        valid, invalid = guardian.filter_old_events(all_events, timeout)

        self.assertEquals(5, len(invalid))
        self.assertEquals(5, len(valid))

    def test_reduce_structure_events(self):
        input_events = list()
        for i in range(1, 5):
            input_events.append({"resource": "cpu", "action": {"events": {"scale": {"up": i, "down": 0}}}})

        for i in range(2, 6):
            input_events.append({"resource": "cpu", "action": {"events": {"scale": {"up": 0, "down": i}}}})

        expected_output = {"cpu": {"events": {"scale": {"up": sum(range(1, 5)), "down": sum(range(2, 6))}}}}

        self.assertEquals(expected_output, guardian.reduce_structure_events(input_events))

    def test_invalid_container_state(self):
        def get_valid_state():
            resources = dict(
                cpu=dict(max=300, current=200, min=50),
                mem=dict(max=8192, current=2048, min=256)
            )

            limits = dict(
                cpu=dict(upper=140, lower=70),
                mem=dict(upper=2000, lower=1000)
            )
            return resources, limits

        # State should be valid
        resources, limits = get_valid_state()
        self.assertFalse(guardian.invalid_container_state(resources, limits))

        # Make resources and limits invalid because unset
        for resource in ["cpu", "mem"]:
            for key in ["max", "min"]:
                resources, limits = get_valid_state()
                resources[resource][key] = guardian.NOT_AVAILABLE_STRING
                self.assertTrue(guardian.invalid_container_state(resources, limits))

            for key in ["upper", "lower"]:
                resources, limits = get_valid_state()
                limits[resource][key] = guardian.NOT_AVAILABLE_STRING
                self.assertTrue(guardian.invalid_container_state(resources, limits))

        for resource in ["cpu", "mem"]:
            # Invalid because max < current
            resources, limits = get_valid_state()
            resources[resource]["max"], resources[resource]["current"] = resources[resource]["current"], \
                                                                         resources[resource]["max"]
            self.assertTrue(guardian.invalid_container_state(resources, limits))

            # Invalid because current < upper
            resources, limits = get_valid_state()
            resources[resource]["current"], limits[resource]["upper"] = limits[resource]["upper"], resources[resource][
                "current"]
            self.assertTrue(guardian.invalid_container_state(resources, limits))

            # Invalid because upper < lower
            resources, limits = get_valid_state()
            limits[resource]["upper"], limits[resource]["lower"] = limits[resource]["lower"], limits[resource]["upper"]
            self.assertTrue(guardian.invalid_container_state(resources, limits))

            # Invalid because lower < min
            resources, limits = get_valid_state()
            resources[resource]["min"], limits[resource]["lower"] = limits[resource]["lower"], resources[resource][
                "min"]
            self.assertTrue(guardian.invalid_container_state(resources, limits))

        # Make resources and limits invalid because no boundary is left between rasl and upr limit
        # for resource in ["cpu", "mem"]:
        #     resources, limits = get_valid_state()
        #     limits[resource]["upper"] = resources[resource]["current"] - resources_boundaries[resource] / 2
        #     self.assertTrue(guardian.invalid_container_state(resources, limits))

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
            "proc.cpu.user": 2.5664364,
            "proc.mem.resident": 1.784324,
            "proc.disk.reads": 6.31534,
            "proc.net.read": 9.56123
        }

        self.assertEquals("300,200,140,2.57,70,50",
                          guardian.get_container_resources_str("cpu", resources_dict, limits_dict, usages_dict))
        self.assertEquals("8192,2048,8000,1.78,7000,256",
                          guardian.get_container_resources_str("mem", resources_dict, limits_dict, usages_dict))
        # TODO Should these tests be used or not?
        # self.assertEquals("200,80,70,6.31,60,50",
        #                  guardian.get_container_resources_str("disk", resources_dict, limits_dict, usages_dict))
        # self.assertEquals("200,80,70,9.56,60,50",
        #                  guardian.get_container_resources_str("net", resources_dict, limits_dict, usages_dict))

    def test_container_energy_str(self):
        resources_dict = dict(
            energy=dict(max=50, current=20, min=0)
        )

        limits_dict = dict(
            energy=dict(upper=30, lower=10)
        )
        self.assertEquals("50,30,20,10,0",
                          guardian.get_container_energy_str(resources_dict, limits_dict))

    def test_adjust_if_invalid_amount(self):
        resource = "cpu"
        structure = {"resources": {"cpu": {"max": 400, "min": 50, "current": 200}}}
        limits = {"resources": {"cpu": {"upper": 150, "lower": 70}}}

        self.assertEquals(70, self.guardian.adjust_if_invalid_amount(70, resource, structure, limits))
        self.assertEquals(100, guardian.adjust_if_invalid_amount(100, resource, structure, limits))
        self.assertEquals(250, guardian.adjust_if_invalid_amount(250, resource, structure, limits))
        self.assertEquals(250, guardian.adjust_if_invalid_amount(260, resource, structure, limits))
        self.assertEquals(250, guardian.adjust_if_invalid_amount(300, resource, structure, limits))

        self.assertEquals(-10, guardian.adjust_if_invalid_amount(-10, resource, structure, limits))
        self.assertEquals(-20, guardian.adjust_if_invalid_amount(-20, resource, structure, limits))
        self.assertEquals(-20, guardian.adjust_if_invalid_amount(-30, resource, structure, limits))
        self.assertEquals(-20, guardian.adjust_if_invalid_amount(-70, resource, structure, limits))

    def test_get_amount_from_percentage_reduction(self):
        resource = "mem"
        structure = {"resources": {"mem": {"max": 4096, "min": 256, "current": 2048}}}
        usages = {"proc.mem.resident": 1000}

        self.assertEquals(-210, guardian.get_amount_from_percentage_reduction(structure, usages, resource, 20))
        # Should max out to 50%
        self.assertEquals(-524, guardian.get_amount_from_percentage_reduction(structure, usages, resource,
                                                                              60))

    def test_get_amount_from_fit_reduction(self):
        resource = "mem"
        structure = {"resources": {"mem": {"max": 4096, "min": 256, "current": 2000}}}
        usages = {"proc.mem.resident": 700}
        limits = {"resources": {"mem": {"upper": 1500, "lower": 1000}}}

        # To properly fit the limit, the usage (700) has to be placed between the upper and lower limit,
        # keeping the current limits difference 1500 - 1000 = 500, so the new limits should be (1200,200)
        # finally, keeping the real resource limit to the upper limit difference 2000 - 1500 = 500, the final
        # current value to apply should be (current)700+(limits difference/2)250+(real_to_upper difference)500 = 1450
        # so the amount to reduce is 2000 - 1450 = 550
        self.assertEquals(-550, guardian.get_amount_from_fit_reduction(structure, usages, resource, limits))

    def test_match_usages_and_limits(self):
        def assertEventEquals(rule, event):
            event_expected_name = guardian.generate_event_name(rule["action"]["events"], rule["resource"])
            self.assertTrue(event_expected_name, event["name"])
            self.assertTrue(structure_name, event["structure"])
            self.assertTrue(rule["action"], event["action"])
            self.assertTrue("event", event["type"])
            self.assertTrue(rule["resource"], event["resource"])

        rule_mem_exceeded_upper = dict(
            _id='mem_exceeded_upper',
            type='rule',
            resource="mem",
            name='mem_exceeded_upper',
            rule=dict(
                {"and": [
                    {">": [
                        {"var": "proc.mem.resident"},
                        {"var": "limits.mem.upper"}]},
                    {"<": [
                        {"var": "limits.mem.upper"},
                        {"var": "structure.mem.max"}]}]}),
            generates="events",
            action={"events": {"scale": {"up": 1}}},
            active=True
        )

        rule_mem_dropped_lower = dict(
            _id='mem_dropped_lower',
            type='rule',
            resource="mem",
            name='mem_dropped_lower',
            rule=dict(
                {"and": [
                    {">": [
                        {"var": "proc.mem.resident"},
                        0]},
                    {"<": [
                        {"var": "proc.mem.resident"},
                        {"var": "limits.mem.lower"}]},
                    {">": [
                        {"var": "limits.mem.lower"},
                        {"var": "structure.mem.min"}]}]}),
            generates="events",
            action={"events": {"scale": {"down": 1}}},
            active=True
        )
        rules = [rule_mem_exceeded_upper, rule_mem_dropped_lower]
        structure_name = "node99"

        resources = dict(
            cpu=dict(max=300, current=200, min=50),
            mem=dict(max=8192, current=2048, min=256),
            disk=dict(max=200, current=80, min=50),
            net=dict(max=200, current=80, min=50),
            energy=dict(max=50, current=20, min=0)
        )

        limits = dict(
            cpu=dict(upper=140, lower=70, boundary=70),
            mem=dict(upper=2000, lower=1000),
            disk=dict(upper=70, lower=60),
            net=dict(upper=70, lower=60),
            energy=dict(upper=30, lower=10)
        )
        usages = {"proc.mem.resident": 1024}

        # No events expected
        self.assertEquals([], guardian.match_usages_and_limits(structure_name, rules, usages, limits, resources))

        # Expect mem underuse event
        usages["proc.mem.resident"] = limits["mem"]["lower"] - 100
        events = guardian.match_usages_and_limits(structure_name, rules, usages, limits, resources)
        if not events:
            self.fail("No events were triggered when expected.")
        else:
            event = events[0]

        assertEventEquals(rule_mem_dropped_lower, event)

        # Expect mem bottleneck event
        usages["proc.mem.resident"] = limits["mem"]["upper"] + 100
        events = guardian.match_usages_and_limits(structure_name, rules, usages, limits, resources)
        if not events:
            self.fail("No events were triggered when expected.")
        else:
            event = events[0]
        assertEventEquals(rule_mem_dropped_lower, event)


if __name__ == '__main__':
    unittest.main()
