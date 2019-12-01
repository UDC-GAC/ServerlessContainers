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

## Serverless environment
The next plot shows how CPU is scaled according to the real usage for a 
cluster of containers running concurrent Big Data TeraSort executions. As it can be 
seen, the allocated CPU (blue line) follows close the usage pattern of the 
workloads executed on the container cluster (orange line). 

On this serverless scenario, the allocated (and billed) CPU tend would 
ideally evolve to match that of the used one, thus having a _**serverless**_
environment with the flexibility and support of the _**container**_ virtualization
technology.

<p align="center">
  <img 
       src="https://s3-eu-west-1.amazonaws.com/jonatan.enes.udc/serverless_containers_website/hybrid_concurrent_serverless.png"
       width="700px" 
       title="serverless Concurrent TeraSort">
</p>

## Energy capping
Serverless Containers has also been used to create an environment where the 
energy of containers is continuously monitored with the option of setting
an energy cap and have it enforced overall. 

This scenario has been developed with the integration of Serverless Containers 
along with the [BDWatchdog](https://github.com/JonatanEnes/BDWatchdog)
and [PowerAPI](https://github.com/powerapi-ng/powerapi) frameworks.
This work was carried out as a joint effort with the [Spirals](https://team.inria.fr/spirals/) 
research group (University of Lille 1 and Inria).

For more information of this use case, you can visit this 
[webpage](http://bdwatchdog.dec.udc.es/energy/index.html).

## About
Serverless Containers has been developed in the Computer Architecture 
Group at the University of A Coruña by Jonatan Enes (jonatan.enes@udc.es), 
Roberto R. Expósito and Juan Touriño.

For more information on this project you can visit its 
[webpage](http://bdwatchdog.dec.udc.es/serverless/index.html).

For precise documentation, please check out this 
[webpage](https://serverlesscontainers.readthedocs.io/en/latest/).
