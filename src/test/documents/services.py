#!/usr/bin/python
# -*- coding: utf-8 -*-
#
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


rebalancer = dict(
    name="rebalancer",
    type="service",
    heartbeat="",
    config=dict(
        WINDOW_TIMELAPSE=10,
        WINDOW_DELAY=10,
        DEBUG=True
    )
)

guardian_service = dict(
    name="guardian",
    type="service",
    heartbeat="",
    config=dict(
        STRUCTURE_GUARDED="container",
        WINDOW_TIMELAPSE=10,
        WINDOW_DELAY=10,
        EVENT_TIMEOUT=100,
        CPU_SHARES_PER_WATT=6,
        DEBUG=True
    )
)

scaler = dict(
    name="scaler",
    type="service",
    heartbeat="",
    config=dict(
        DEBUG=True,
        POLLING_FREQUENCY=5,
        REQUEST_TIMEOUT=30
    )
)

database_snapshoter = dict(
    name="database_snapshoter",
    type="service",
    heartbeat="",
    config=dict(
        POLLING_FREQUENCY=5,
        DEBUG=True
    )
)

structures_snapshoter = dict(
    name="structures_snapshoter",
    type="service",
    heartbeat="",
    config=dict(
        POLLING_FREQUENCY=5,
        PERSIST_APPS=False
    )
)

refeeder = dict(
    name="refeeder",
    type="service",
    heartbeat="",
    config=dict(
        WINDOW_TIMELAPSE=7,
        WINDOW_DELAY=30,
        DEBUG=True
    )
)

sanity_checker = dict(
    name="sanity_checker",
    type="service",
    heartbeat="",
    config=dict(
        DELAY=30,
        DEBUG=True
    )
)

energy_manager = dict(
    name="energy_manager",
    type="service",
    heartbeat="",
    config=dict(
        POLLING_FREQUENCY=10,
        DEBUG=True
    )
)
