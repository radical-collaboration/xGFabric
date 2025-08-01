start=$(date '+%s.%N')

module add openfoam/10.0/gcc/8.5.0 > /dev/null 2>&1

echo $destination

mkdir $destination
unzip $folder_name -d $destination
mv $destination/$folder_name/* $destination
rm $destination/$folder_name

python3 replace.py "$destination/system/decomposeParDict" "$destination/system/decomposeParDict" @ $NSLOTS

cd $destination

if [ "$threads" -eq 1 ]; then
    p_start=$(date '+%s.%N')
    porousSimpleFoam | tee "../logs/$threads-$destination"
    p_stop=$(date '+%s.%N')
    p_elapsed=$(bc -l <<< "$p_stop - $p_start")
else
    decomposePar -fileHandler uncollated -force
    mpirun -n $NSLOTS porousSimpleFoam -parallel | tee "../logs/${threads}-${destination}.log"
    echo "Reconstruction started"
    reconstructPar
fi

stop=$(date '+%s.%N')
elapsed=$(bc -l <<< "$stop - $start")

cd ..

echo "Run of $destination with $NSLOTS took $elapsed sec" >> ./result_time
