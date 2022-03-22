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


import time
import json
import requests
import gzip
import io

from requests import ReadTimeout


class OpenTSDBServer:
    __OPENTSDB_URL = "opentsdb"
    __OPENTSDB_PORT = 4242
    NO_METRIC_DATA_DEFAULT_VALUE = 0  # -1
    __TIMEOUT = 5

    def __init__(self, opentsdb_url=None, opentsdb_port=None):
        if not opentsdb_url:
            opentsdb_url = self.__OPENTSDB_URL
        if not opentsdb_port:
            opentsdb_port = self.__OPENTSDB_PORT
        else:
            try:
                opentsdb_port = int(opentsdb_port)
            except ValueError:
                opentsdb_port = self.__OPENTSDB_PORT

        self.server = "http://{0}:{1}".format(opentsdb_url, str(opentsdb_port))
        self.session = requests.Session()

    def close_connection(self):
        self.session.close()

    def send_json_documents(self, json_documents):
        headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}
        out = io.BytesIO()
        with gzip.GzipFile(fileobj=out, mode="w") as f:
            f.write(json.dumps(json_documents).encode())

        try:
            r = self.session.post("{0}/{1}".format(self.server, "api/put"), headers=headers, data=out.getvalue(),
                                  timeout=self.__TIMEOUT)
            if r.status_code != 204:
                return False, {"error": r.json()}
            else:
                return True, {}
        except ReadTimeout:
            return False, {"error": "Server timeout"}
        except Exception as e:
            return False, {"error": str(e)}

    def get_points(self, query, tries=3):
        try:
            r = self.session.post("{0}/{1}".format(self.server, "api/query"), data=json.dumps(query),
                                  headers={'content-type': 'application/json', 'Accept': 'application/json'})
            if r.status_code == 200:
                return json.loads(r.text)
            elif r.status_code == 400:
                error_message = json.loads(r.content)["error"]["message"]
                if "No such name for 'tagv'" in error_message:
                    return {}
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise e
            else:
                self.get_points(query, tries)


    def get_structure_timeseries(self, tags, window_difference, window_delay, retrieve_metrics, generate_metrics,
                                 downsample=5):
        usages = dict()
        subquery = list()
        for metric in retrieve_metrics:
            usages[metric] = self.NO_METRIC_DATA_DEFAULT_VALUE
            subquery.append(dict(aggregator='zimsum', metric=metric, tags=tags, downsample=str(downsample) + "s-avg"))

        start = int(time.time() - (window_difference + window_delay))
        end = int(time.time() - window_delay)
        query = dict(start=start, end=end, queries=subquery)
        result = self.get_points(query)

        if result:
            for metric in result:
                dps = metric["dps"]
                summatory = sum(dps.values())
                if len(dps) > 0:
                    average_real = summatory / len(dps)
                else:
                    average_real = 0
                usages[metric["metric"]] = average_real

        final_values = dict()

        for value in generate_metrics:
            final_values[value] = self.NO_METRIC_DATA_DEFAULT_VALUE
            for metric in generate_metrics[value]:
                if metric in usages and usages[metric] != self.NO_METRIC_DATA_DEFAULT_VALUE:
                    final_values[value] += usages[metric]

        return final_values
