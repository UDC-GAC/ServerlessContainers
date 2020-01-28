This framework is used to **scale** the **resources** of a **container**, 
or a group of containers, both **dynamically and in real time**, so that the 
limits placed on such resources evolve to be just above the usage. 

On the one hand, from a traditional **virtual machine** and **Cloud** 
perspective, this approach is similar to the on-demand and pay 
per usage resource provisioning. The main difference would be that on this 
case, the limits can be changed multiple times during execution instead 
of being specified only once at the instantiation phase.

On the other hand, this approach is also close to the **serverless** 
paradigm on the fact that the container, and all of the processes 
running on it, can not trust the pool of resources exposed to them as
such resources limits can vary according to their usage (e.g., if the
CPU usage increases, the CPU limit should also be raised via adding more
cores).

Combining both of these approaches, this framework comes up with a solution
so that virtual infrastructure units, such as software containers (e.g.,
LXC, Docker), can benefit from having a resource management that implements
a serverless scenario. Among other perks, the main benefits of this 
framework include:

* A higher resource efficiency, those containers with a low resource usage 
will also be given a smaller set of resources, while those with a higher usage, 
will have a larger set of resources available over time.

* Pay per usage billing policy, in the same way as the Cloud platforms, 
only the used resources should be considered for billing.

* The flexibility of supporting and using containers, which are virtually
highly similar to virtual machines and, thus, can be used to deploy a wide
arrange of applications.

The next image shows the evolution of the CPU limit placed on a 
container over time.

![Time series](img/use_case/timeseries.png)

![Areas](img/use_case/integrals.png)


