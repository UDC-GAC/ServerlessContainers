
# NODE LIMITS
./build/tsdb mkmetric limit.cpu.lower
./build/tsdb mkmetric limit.cpu.upper
./build/tsdb mkmetric limit.mem.lower
./build/tsdb mkmetric limit.mem.upper
./build/tsdb mkmetric limit.disk.lower
./build/tsdb mkmetric limit.disk.upper
./build/tsdb mkmetric limit.net.lower
./build/tsdb mkmetric limit.net.upper

# NODE RESOURCES
./build/tsdb mkmetric node.cpu.current
./build/tsdb mkmetric node.cpu.max
./build/tsdb mkmetric node.cpu.min
./build/tsdb mkmetric node.mem.current
./build/tsdb mkmetric node.mem.max
./build/tsdb mkmetric node.mem.min
./build/tsdb mkmetric node.disk.current
./build/tsdb mkmetric node.disk.max
./build/tsdb mkmetric node.disk.min
./build/tsdb mkmetric node.net.current
./build/tsdb mkmetric node.net.max
./build/tsdb mkmetric node.net.min
