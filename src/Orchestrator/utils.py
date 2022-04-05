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

from flask import g
import os

import src.StateDatabase.couchdb as couchDB

MAX_TRIES = 10
BACK_OFF_TIME_MS = 500
COUCHDB_URL = os.getenv('COUCHDB_URL')
if not COUCHDB_URL:
    COUCHDB_URL = "couchdb"


def get_db():
    global COUCHDB_URL
    """Opens a new database connection if there is none yet for the current application context."""
    if not hasattr(g, 'db_handler'):
        g.db_handler = couchDB.CouchDBServer(couchdb_url=COUCHDB_URL)
    return g.db_handler
