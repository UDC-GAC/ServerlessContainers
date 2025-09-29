# Get initial data
CPID=$1
MAJOR_MINOR=$2

service_bytes_file=/sys/fs/cgroup/blkio/system.slice/apptainer-$CPID.scope/blkio.throttle.io_service_bytes_recursive
serviced_file=/sys/fs/cgroup/blkio/system.slice/apptainer-$CPID.scope/blkio.throttle.io_serviced_recursive

read_before_bytes=$(cat $service_bytes_file | grep "$MAJOR_MINOR Read" | awk '{print $3}')
read_before_ops=$(cat $serviced_file | grep "$MAJOR_MINOR Read" | awk '{print $3}')

write_before_bytes=$(cat $service_bytes_file | grep "$MAJOR_MINOR Write" | awk '{print $3}')
write_before_ops=$(cat $serviced_file | grep "$MAJOR_MINOR Write" | awk '{print $3}')

sleep 1

# Get data after interval
read_after_bytes=$(cat $service_bytes_file | grep "$MAJOR_MINOR Read" | awk '{print $3}')
read_after_ops=$(cat $serviced_file | grep "$MAJOR_MINOR Read" | awk '{print $3}')

write_after_bytes=$(cat $service_bytes_file | grep "$MAJOR_MINOR Write" | awk '{print $3}')
write_after_ops=$(cat $serviced_file | grep "$MAJOR_MINOR Write" | awk '{print $3}')

# Calculate stas
read_delta_bytes=$((read_after_bytes - read_before_bytes))
write_delta_bytes=$((write_after_bytes - write_before_bytes))

read_delta_ops=$((read_after_ops - read_before_ops))
write_delta_ops=$((write_after_ops - write_before_ops))

read_avg_bytes_per_op=$((read_delta_bytes / (read_delta_ops>0 ? read_delta_ops : 1)))
write_avg_bytes_per_op=$((write_delta_bytes / (write_delta_ops>0 ? write_delta_ops : 1)))

# Print output
echo "$((read_avg_bytes_per_op/1024)) $((write_avg_bytes_per_op/1024))"