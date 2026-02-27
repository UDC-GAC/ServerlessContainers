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


import time
import json
import requests
import gzip
import io
import yaml
import os

from requests import ReadTimeout


class OpenTSDBServer:
    __OPENTSDB_URL = "opentsdb"
    __OPENTSDB_PORT = 4242
    NO_METRIC_DATA_DEFAULT_VALUE = -1
    __TIMEOUT = 5

    def __init__(self, opentsdb_url=None, opentsdb_port=None):

        serverless_path = os.environ['SERVERLESS_PATH']
        config_file = serverless_path + "/services_config.yml"
        with open(config_file, "r") as f:
            config = yaml.load(f, Loader=yaml.FullLoader)

        if not opentsdb_url:
            #opentsdb_url = self.__OPENTSDB_URL
            opentsdb_url = config['OPENTSDB_URL']
        if not opentsdb_port:
            #opentsdb_port = self.__OPENTSDB_PORT
            opentsdb_port = config['OPENTSDB_PORT']
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

    def get_structure_timeseries(self, tags, window_difference, window_delay, retrieve_metrics, generate_metrics, downsample=5):
        result = self.get_structure_timeseries_bulk(list(tags.keys())[0], [list(tags.values())[0]],
                                                    window_difference, window_delay, retrieve_metrics,
                                                    generate_metrics, downsample)
        return next(iter(result.values()))

    def get_structure_timeseries_bulk(self, tag_key, structures, window_difference, window_delay, retrieve_metrics, generate_metrics, downsample=5):
        # Build query info
        tags = {tag_key: "|".join(structures)}
        usages, subqueries = {}, []
        for metric in retrieve_metrics:
            subqueries.append(dict(aggregator='zimsum', metric=metric, tags=tags, downsample=str(downsample) + "s-avg"))
            for structure_name in structures:
                usages.setdefault(structure_name, {})[metric] = self.NO_METRIC_DATA_DEFAULT_VALUE
        start = int(time.time() - (window_difference + window_delay))
        end = int(time.time() - window_delay)
        query = dict(start=start, end=end, queries=subqueries)

        # Send query and process result
        result = self.get_points(query)
        if result:
            for entry in result:
                structure_name = str(entry["tags"][tag_key])
                dps = entry["dps"]
                average_real = sum(dps.values()) / len(dps) if len(dps) > 0 else 0
                usages[structure_name][entry["metric"]] = average_real

        # Transform retrieved metrics from OpenTSDB to generated metrics
        final_values = {}
        for structure_name in structures:
            final_values[structure_name] = {}
            for gen_metric, sub_metrics in generate_metrics.items():
                values = []
                for sub_metric in sub_metrics:
                    value = usages[structure_name].get(sub_metric, self.NO_METRIC_DATA_DEFAULT_VALUE)
                    if value != self.NO_METRIC_DATA_DEFAULT_VALUE:
                        values.append(value)
                final_values[structure_name][gen_metric] = sum(values) if values else self.NO_METRIC_DATA_DEFAULT_VALUE

        return final_values
