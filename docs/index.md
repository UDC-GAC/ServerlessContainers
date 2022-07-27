![Logo](img/logo.png){: style="max-width:25%; margin-left: 35%"}

# Introduction

Serverless Containers is a framework that is able to **dynamically scale a
container resources** (_e.g., CPU, memory, disk and network_), at any moment 
and in real-time. With this feature it is possible to implement several interesting policies 
for resource management. Currently, two policies are supported with this framework:

* _**Serverless**_, used to adapt the resources according to the real usage the containers make
* _**Energy capping**_, where CPU is adjusted in order to control the energy that a containers is consuming

For a brief summary of this tool you can visit its 
[homepage](http://bdwatchdog.dec.udc.es/serverless/index.html) website. 
If you want to see data from real experiments where this tool was used, you can 
visit [this demo](http://bdwatchdog.dec.udc.es/BDWatchdog/TimeseriesViewer/demo.html).
Finally, for the uncommented source code you can visit its 
[GitHub](https://github.com/UDC-GAC/ServerlessContainers).


While this documentation webpage gives a detailed description of the 
framework, it does not delve into any technical detail. In case you are
interested on such details, Serverless Containers has also been the subject of a publication in 
**Future Generation Computer Systems (FGCS)**, which is available 
[online](https://www.sciencedirect.com/science/article/pii/S0167739X19310015).
([preprint](http://bdwatchdog.dec.udc.es/articles/serverless_containers.pdf))
In this publication, the framework is thoroughly described, along with several experimental examples.



This webpage has been structured with the following sections:

1. [Serverless policy](serverless_policy.md): 
Where a summary of the serverless policy and its use case is given, as well
as its underlying concepts and ideas to implement it.

2. [Energy capping policy](energy_policy.md): 
The energy capping policy is presented.

3. [Architecture](architecture.md): 
Which briefly describes the architecture and the design used.

4. [Deployment](deployment.md): 
In this section it is described how to deploy the framework overall. 
Some guidelines are also provided.

5. [Sponsors](sponsors.md): 
Some comments on the backers and sponsors of this framework.

6. [Homepage (external)](http://bdwatchdog.dec.udc.es/serverless/index.html): 
The institutional webpage of this framework. 

7. [Source Code (external)](code/src/index.html): 
If you are interested on the code and inline code documentation. 
