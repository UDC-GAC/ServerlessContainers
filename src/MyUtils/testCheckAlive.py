import time
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from src.MyUtils.CheckAlive import service_is_alive, classify_service, sort_services_dead_and_alive


class CheckAliveTest(TestCase):

    def test_service_is_alive(self):
        fake_service = dict(
            name="bogus",
            type="service",
            heartbeat="",
            config=dict(
            )
        )
        time_window = 10

        del (fake_service["heartbeat"])
        self.assertFalse(service_is_alive(fake_service, time_window))

        fake_service["heartbeat"] = "bogus"
        self.assertFalse(service_is_alive(fake_service, time_window))

        fake_service["heartbeat"] = -20
        self.assertFalse(service_is_alive(fake_service, time_window))

        fake_service["heartbeat"] = time.time() - 2 * time_window
        self.assertFalse(service_is_alive(fake_service, time_window))

        fake_service["heartbeat"] = time.time() - 0.5 * time_window
        self.assertTrue(service_is_alive(fake_service, time_window))

    @patch('MyUtils.CheckAlive.requests.get')
    def test_classify_service(self, mock_get):
        fake_service = dict(
            name="bogus",
            type="service",
            heartbeat="",
            config=dict(
            )
        )

        self.assertEqual(first="Others", second=classify_service(fake_service["name"]))

        fake_service["name"] = "Atop_node34"
        self.assertEqual(first="Atops", second=classify_service(fake_service["name"]))

        fake_service["name"] = "Turbostat_node34"
        self.assertEqual(first="Turbostats", second=classify_service(fake_service["name"]))

        fake_service["name"] = "c10-10_rescaler"
        self.assertEqual(first="Node-Rescalers", second=classify_service(fake_service["name"]))

        services = list()
        fake_service["heartbeat"] = time.time()
        for i in range(5):
            service = fake_service.copy()
            service["heartbeat"] -= i * 5
            services.append(service)

        # With alive REST services
        mock_get.return_value.status_code = 200
        alive_rest_services = [("bogus0", "bogus0.com", "4000"), ("bogus1", "bogus1.com", "4000")]

        time_window_allowed = 14
        dead, alive = sort_services_dead_and_alive(services, alive_rest_services, time_window_allowed)

        self.assertEqual(first=5, second=len(alive))
        self.assertEqual(first=2, second=len(dead))

        # With dead rest services
        failed_rest_services = [("bogus2", "bogus2.com", "4000"), ("bogus3", "bogus3.com", "4000")]
        mock_get.return_value.status_code = 404
        dead, alive = sort_services_dead_and_alive(services, failed_rest_services, time_window_allowed)
        self.assertEqual(first=3, second=len(alive))
        self.assertEqual(first=4, second=len(dead))


        errored_rest_services = [("bogus4", "bogus4.com", "4000")]
        mock_get.side_effect = requests.exceptions.ConnectionError
        dead, alive = sort_services_dead_and_alive([], errored_rest_services, time_window_allowed)
        self.assertEqual(first=0, second=len(alive))
        self.assertEqual(first=1, second=len(dead))
