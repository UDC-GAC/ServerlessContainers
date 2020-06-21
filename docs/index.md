![Logo](img/logo.png){: style="max-width:25%; margin-left: 40%"}

The Serverless Containers framework is able to **dynamically scale a 
container resource limit (_e.g., CPU, Memory, disk and network_) 
in order to adapt them to the real usage**, at any moment and in 
real-time. This feature in the way that is implemented, creates
a serverless environment which supports containers.

* For a brief summary of this tool you can visit its 
[homepage](http://bdwatchdog.dec.udc.es/serverless/index.html) website.
* In order to see data from real experiments where this tool was used, 
you can visit [this demo](http://bdwatchdog.dec.udc.es/BDWatchdog/TimeseriesViewer/demo.html).
* For the uncommented source code you can visit its 
[GitHub](https://github.com/UDC-GAC/ServerlessContainers).

Serverless Containers has also been the subject of a publication in 
**Future Generation Computer Systems (FGCS)**, which is available 
[online](https://www.sciencedirect.com/science/article/pii/S0167739X19310015).
([preprint](http://bdwatchdog.dec.udc.es/articles/serverless_containers.pdf))
In this publication the framework is thoroughly described with all 
technichal detail along with several experimental examples.

This documentation webpage gives a more detailed description of the 
framework but without delving into the technichal details as in the 
available publication. The webpage has been structured with the 
following sections:

1. [Use case](use_case.md): 
This section summarizes the core use case of this framework as well
as its underlying concepts and ideas to implement it and to create 
the serverless environment.

2. [Architecture](architecture.md): 
Which briefly describes the architecture and design used.

3. [Deployment](deployment.md): 
In this section it is described how to deploy the framework overall. 
Some guidelines are also provided.

4. [Quickstart](quickstart.md):
In this section a quickstart guide is provided to show how two containers
would be supported and transitioned from a traditional resource management
to work with a serverless environment.

5. [Configuration](configuration.md):
In this section a few, key configuration parameters are explained to 
tune the framework's behaviour between the two extremes, a traditional 
instance or an aggressive serverless environment.

6. [Sponsors](sponsors.md): 
Some comments on the backers and sponsors of this framework.

7. [Homepage (external)](http://bdwatchdog.dec.udc.es/serverless/index.html): 
the institutional webpage of this framework. 

8. [Source Code (external)](code/src/index.html): 
If you are interested on the code and inline code documentation. 

