# Copyright (c) 2019 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es, jonatan.enes.alvarez@gmail.com)
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


import unittest
import src.Rescaler.ClusterScaler as scaler


class ClusterRescalerTest(unittest.TestCase):
    scaler = scaler

    def test_apply_request(self):
        host_info_cache = {
            "dante" : {
                "name": "dante",
                "subtype": "host",
                "host": "dante",
                "type": "structure",
                "resources": {
                "mem": {
                  "max": 30000,
                  "free": 16384
                },
                "cpu": {
                  "core_usage_mapping": {
                    "0": {
                      "node0": 100,
                      "free": 0
                    },
                    "1": {
                      "node1": 100,
                      "free": 0
                    },
                    "2": {
                      "node0": 100,
                      "free": 0
                    },
                    "3": {
                      "node1": 100,
                      "free": 0
                    },
                    "4": {
                      "node2": 100,
                      "free": 0
                    },
                    "5": {
                      "node3": 100,
                      "free": 0
                    },
                    "6": {
                      "node2": 100,
                      "free": 0
                    },
                    "7": {
                      "node3": 100,
                      "free": 0
                    }
                  },
                  "max": 800,
                  "free": 0
                }
                }
            }
        }

        RescaleCpuDown = {
            "amount": -150,
            "resource": "cpu",
            "host": "dante",
            "structure": "node1"
        }
        RescaleCpuUp = {
            "amount": 40,
            "resource": "cpu",
            "host": "dante",
            "structure": "node0"
        }

        node0_real_resources = {
            "cpu": {
              "cpu_allowance_limit": 200,
              "cpu_num": "0,2",
              "effective_cpu_limit": 200,
              "effective_num_cpus": 2
            },
            "mem": {
              "mem_limit": 4096,
              "unit": "M"
            }
        }

        node0_db_resources = {
            "name": "node0",
            "subtype": "container",
            "host": "dante",
            "type": "structure",
            "resources": {
                "mem": {
                  "current": 4096,
                  "max": 8192,
                  "min": 256
                },
                "cpu": {
                  "current": 200,
                  "max": 250,
                  "min": 10
                }
                }
            }

        node1_real_resources = {
            "cpu": {
                "cpu_allowance_limit": 200,
                "cpu_num": "1,3",
                "effective_cpu_limit": 200,
                "effective_num_cpus": 2
            },
            "mem": {
                "mem_limit": 4096,
                "unit": "M"
            }
        }

        node1_db_resources = {
            "name": "node1",
            "subtype": "container",
            "host": "dante",
            "type": "structure",
            "resources": {
            "mem": {
              "current": 4096,
              "max": 8192,
              "min": 256
            },
            "cpu": {
              "current": 200,
              "max": 250,
              "min": 10
            }
            }
        }
        #
        # ## CPU ##
        # # Can't rescale up as no resources are available
        # with self.assertRaises(ValueError):
        #     scaler.apply_request(RescaleCpuUp, node0_real_resources, node0_db_resources, host_info_cache)
        #
        # expected_cpu_dict = {"cpu":{"cpu_num":"1","cpu_allowance_limit":50}}
        # retrieved_cpu_dict, host_info_cache = scaler.apply_request(RescaleCpuDown, node1_real_resources, node1_db_resources, host_info_cache)
        # self.assertEquals(expected_cpu_dict,retrieved_cpu_dict)
        # self.assertEquals(host_info_cache["dante"]["resources"]["cpu"]["free"], 150)
        #
        # # Now we shluld be able to scale up
        # expected_cpu_dict = {"cpu": {"cpu_num": "0,2,1", "cpu_allowance_limit": 240}}
        # retrieved_cpu_dict, host_info_cache = scaler.apply_request(RescaleCpuUp, node0_real_resources,
        #                                                            node0_db_resources, host_info_cache)
        # self.assertEquals(host_info_cache["dante"]["resources"]["cpu"]["free"], 110)
        # self.assertEquals(expected_cpu_dict, retrieved_cpu_dict)
        #
        # node0_real_resources["cpu"]["cpu_allowance_limit"] = 240
        # node0_db_resources["resources"]["cpu"]["cpu_num"] = "0-2"
        # # Should thrown an error as it is over the limit
        # with self.assertRaises(ValueError):
        #     scaler.apply_request(RescaleCpuUp, node0_real_resources, node0_db_resources, host_info_cache)
        #
        # node1_real_resources["cpu"]["cpu_allowance_limit"] = 50
        # node1_db_resources["resources"]["cpu"]["cpu_num"] = "1"
        # RescaleCpuDown["amount"] = -60
        # # Should thrown an error as it is lower than 0
        # with self.assertRaises(ValueError):
        #     scaler.apply_request(RescaleCpuDown, node1_real_resources, node1_db_resources, host_info_cache)
        #


        ## MEM ##

