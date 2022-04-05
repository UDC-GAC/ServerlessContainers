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

containers = ["node0", "node1", "node2", "node3",
              "node4", "node5", "node6", "node7",
              "node8", "node9", "node10", "node11",
              "node12", "node13", "node14", "node15",
              "node16", "node17", "node18", "node19",
              "node20", "node21", "node22", "node23",
              "node24", "node25", "node26", "node27",
              "node28", "node29", "node30", "node31"]
applications = ["app1"]

base_limits = dict(
    type='limit',
    name="base_container",
    resources=dict(
        cpu=dict(upper=500, lower=400, boundary=125),
        mem=dict(upper=44000, lower=40000, boundary=3072),
        disk=dict(upper=100, lower=20, boundary=10),
        net=dict(upper=100, lower=20, boundary=10),
        energy=dict(upper=15, lower=5, boundary=3)
    )
)

