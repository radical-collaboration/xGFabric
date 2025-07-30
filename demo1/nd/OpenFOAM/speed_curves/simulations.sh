sh runme.sh -t=64 -n=1
echo "Submitted a simulation with 64 threads on 1 node."
sleep 2

sh runme.sh -t=64 -n=2
echo "Submitted a simulation with 64 threads on 2 nodes."
sleep 2

sh runme.sh -t=64 -n=4
echo "Submitted a simulation with 64 threads on 4 nodes."
