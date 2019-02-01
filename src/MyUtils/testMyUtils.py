from unittest import TestCase

from MyUtils.MyUtils import generate_request_name, get_cpu_list


class MyUtilsTest(TestCase):

    def test_generate_request_name(self):
        for resource in ["cpu", "mem"]:
            expected = resource.title() + "RescaleUp"
            TestCase.assertEqual(self, first=expected, second=generate_request_name(100, resource))
            expected = resource.title() + "RescaleDown"
            TestCase.assertEqual(self, first=expected, second=generate_request_name(-100, resource))

            with self.assertRaises(ValueError):
                generate_request_name(None, resource)

            with self.assertRaises(ValueError):
                generate_request_name("bogus", resource)

            with self.assertRaises(ValueError):
                generate_request_name(0, resource)

    def test_get_cpu_list(self):
        TestCase.assertEqual(self, first=['1', '2', '3'], second=get_cpu_list("1-3"))
        TestCase.assertEqual(self, first=['0', '1', '2', '5'], second=get_cpu_list("0-2,5"))
        TestCase.assertEqual(self, first=['1', '2', '3', '5', '4'], second=get_cpu_list("1-3,5,4"))
        TestCase.assertEqual(self, first=['1', '2', '4', '5', '6', '9'], second=get_cpu_list("1-2,4-6,9"))
