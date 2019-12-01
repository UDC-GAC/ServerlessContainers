# Serverless Containers

[![Build Status](https://travis-ci.com/JonatanEnes/ServerlessContainers.svg?branch=master)](https://travis-ci.com/JonatanEnes/ServerlessContainers)

<p align="center">
  <img src="https://s3-eu-west-1.amazonaws.com/jonatan.enes.udc/serverless_containers_website/logo_serverless.png" width="150" title="Logo">
</p>

This project provides a framework to implement a **_serverless_** environments 
that supports **_containers_**, or, in other words, containers are deployed 
and executed with their resources managed following the serverless paradigm.
To implement such environment, several policies of resource scaling are 
available including scaling the resources limits to fit them according to the
usage, in real time.

The resources that can be scaled and managed with this frameworks are the
**CPU, memory, disk and network** and the container engine supported is 
**LXD** and **LXC**.

## Example
The next plot shows how CPU is scaled according to the real usage for a 
cluster of containers running concurrent Big Data TeraSort executions.

<p align="center">
  <img src="https://s3-eu-west-1.amazonaws.com/jonatan.enes.udc/serverless_containers_website/hybrid_concurrent_serverless.png" width="800px" title="Logo" alt="serverless Concurrent TeraSort" style="margin:20px;">
</p>

## About
Serverless Containers has been developed in the Computer Architecture 
Group at the University of A Coruña by Jonatan Enes (jonatan.enes@udc.es), 
Roberto R. Expósito and Juan Touriño.

For more information on this project's you can visit its 
[webpage](http://bdwatchdog.dec.udc.es/serverless/index.html).
