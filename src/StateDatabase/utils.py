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


import src.StateDatabase.couchdb as couchDB


class CouchDBUtils:

    def __init__(self):
        self.handler = couchDB.CouchDBServer()

    def close_connection(self):
        self.handler.close_connection()

    def create_db(self, database):
        if not self.handler.database_exists(database):
            if self.handler.create_database(database):
                print("Database " + database + " created")
            else:
                print("Database " + database + " couldn't be created")
        else:
            print("Database " + database + " already exists")

    def remove_db(self, database):
        if self.handler.database_exists(database):
            if self.handler.remove_database(database):
                print("Database " + database + " removed")
            else:
                print("Database " + database + " couldn't be removed")
        else:
            print("Database " + database + " doesn't exist")
