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


from unittest import TestCase

from src.MyUtils.MyUtils import generate_request_name, get_cpu_list


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
