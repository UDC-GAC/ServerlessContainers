if [ $# -ne 1 ];
    then echo "illegal number of parameters"
    exit 1
fi
BANDWIDTH=$(($1 * 1024 * 1024))
bash set_bandwidth.sh node0 253:2 $BANDWIDTH
bash set_bandwidth.sh node1 253:3 $BANDWIDTH
bash set_bandwidth.sh node2 253:4 $BANDWIDTH
bash set_bandwidth.sh node3 253:5 $BANDWIDTH
