# Serverless Containers
[![Build Status](https://travis-ci.com/JonatanEnes/ServerlessContainers.svg?branch=master)](https://travis-ci.com/JonatanEnes/ServerlessContainers)

This project provides a framework to implement a _serverless_ environments 
that supports containers, or, in other words, containers are deployed 
and executed with their resources managed following the serverless paragidm.
To implement such environment, several policies of resource scaling are 
available including scaling the resources limits to fit them according to the
usage, in real time.

The resources that can be scaled and managed with this frameworks are the
**CPU, memory, disk and network** and the container engine supported is 
**LXD** and **LXC**.

The next plot shows how CPU is scaled according to the real usage for a 
cluster of containers running concurrent Big Data TeraSort executions.
![serverless Concurrent TeraSort](https://s3-eu-west-1.amazonaws.com/jonatan.enes.udc/serverless_containers_website/hybrid_concurrent_serverless.png)

For more information on this project's you can visit its 
[webpage](http://bdwatchdog.dec.udc.es/serverless/index.html).


