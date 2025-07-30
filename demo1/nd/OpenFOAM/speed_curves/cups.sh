source ~/.bashrc
conda activate xgfabric

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
    
    p_start=$(date '+%s.%N')

    mpirun -n $NSLOTS porousSimpleFoam -parallel | tee "../logs/${threads}-${destination}.log"
    
    p_stop=$(date '+%s.%N')
    p_elapsed=$(bc -l <<< "$p_stop - $p_start")
    
    echo "Reconstruction started"
    reconstructPar
fi

stop=$(date '+%s.%N')
elapsed=$(bc -l <<< "$stop - $start")

cd ..

sh export.sh $destination 5

# echo "Run of $destination on $(date '+%y-%m-%d_%H_%M_%S') and $nodes nodes till $seciteration sec/iteration took $elapsed sec ($p_elapsed);" >> ./result_time
echo "Run of $destination on $(date '+%y-%m-%d_%H_%M_%S') and $nodes nodes ($elapsed sec total) and ($p_elapsed sec in computation);" >> ./result_time
