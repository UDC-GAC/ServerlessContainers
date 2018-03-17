import unittest
import Guardian as guardian
import time
import copy


class GuardianTest(unittest.TestCase):

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
        scale_invalid3 = {"scale": {"down": 1, "up": 3}}

        with self.assertRaises(ValueError):
            guardian.generate_event_name(scale_invalid1, "cpu")

        with self.assertRaises(ValueError):
            guardian.generate_event_name(scale_invalid2, "cpu")

        with self.assertRaises(ValueError):
            guardian.generate_event_name(scale_invalid3, "cpu")

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

        usages_dict_empty = {
            "proc.cpu.user": guardian.NO_METRIC_DATA_DEFAULT_VALUE,
            "proc.mem.resident": guardian.NO_METRIC_DATA_DEFAULT_VALUE,
            "proc.disk.reads": guardian.NO_METRIC_DATA_DEFAULT_VALUE,
            "proc.net.read": guardian.NO_METRIC_DATA_DEFAULT_VALUE
        }

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
        # TODO
        #self.assertEquals("200,80,70,6.31,60,50",
        #                  guardian.get_container_resources_str("disk", resources_dict, limits_dict, usages_dict))
        #self.assertEquals("200,80,70,9.56,60,50",
        #                  guardian.get_container_resources_str("net", resources_dict, limits_dict, usages_dict))


    def test_adjust_if_invalid_amount(self):
        resource = "cpu"
        structure = {"resources":{"cpu":{"max": 400, "min":50, "current": 200}}}
        limits = {"resources":{"cpu":{"upper": 150, "lower": 70}}}

        self.assertEquals(70,guardian.adjust_if_invalid_amount(70, resource, structure, limits))
        self.assertEquals(100, guardian.adjust_if_invalid_amount(100, resource, structure, limits))
        self.assertEquals(250, guardian.adjust_if_invalid_amount(250, resource, structure, limits))
        self.assertEquals(250, guardian.adjust_if_invalid_amount(260, resource, structure, limits))
        self.assertEquals(250, guardian.adjust_if_invalid_amount(300, resource, structure, limits))

        self.assertEquals(-10, guardian.adjust_if_invalid_amount(-10, resource, structure, limits))
        self.assertEquals(-20, guardian.adjust_if_invalid_amount(-20, resource, structure, limits))
        self.assertEquals(-20, guardian.adjust_if_invalid_amount(-30, resource, structure, limits))
        self.assertEquals(-20, guardian.adjust_if_invalid_amount(-70, resource, structure, limits))





if __name__ == '__main__':
    unittest.main()
