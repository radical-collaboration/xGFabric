started_at=$(date '+%s.%N')
echo "$file,$submitted_at,$started_at,$num_cores" >> data/times.csv
sleep 1
