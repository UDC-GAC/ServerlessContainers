
# NODE LIMITS
./build/tsdb mkmetric limit.cpu.lower
./build/tsdb mkmetric limit.cpu.upper
./build/tsdb mkmetric limit.memory.lower
./build/tsdb mkmetric limit.memory.upper
./build/tsdb mkmetric limit.disk.lower
./build/tsdb mkmetric limit.disk.upper
./build/tsdb mkmetric limit.network.lower
./build/tsdb mkmetric limit.network.upper

# NODE RESOURCES
./build/tsdb mkmetric node.cpu.current
./build/tsdb mkmetric node.cpu.max
./build/tsdb mkmetric node.cpu.min
./build/tsdb mkmetric node.memory.current
./build/tsdb mkmetric node.memory.max
./build/tsdb mkmetric node.memory.min
./build/tsdb mkmetric node.disk.current
./build/tsdb mkmetric node.disk.max
./build/tsdb mkmetric node.disk.min
./build/tsdb mkmetric node.network.current
./build/tsdb mkmetric node.network.max
./build/tsdb mkmetric node.network.min