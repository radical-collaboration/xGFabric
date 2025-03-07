# 1. Install openfoam if needed
# https://openfoam.org/download/10-ubuntu/

# 2. Load openfoam
# module load openfoam/10.0/gcc/8.5.0 # For ND cluster
source /opt/openfoam10/etc/bashrc # For UCSB pseudo cluster

# 3. Load most recent online data # Not working on ND as of now
b=$(/sharedfs/cups-data/senspot-get -W woof://169.231.230.76/sharedfs/cups-data/daviscupsout)
vals=$(awk -F" " '{print $1}' <<< "$b")
windspeed=$(awk -F":" '{print $6}' <<< "$vals")
winddir=$(awk -F":" '{print $7}' <<< "$vals")

# 4. Unpack zip and update it with data
python3 unzip_and_update.py $windspeed $winddir --file cfd_test.zip

# 5. Run solver to perform the calculation
cd small_structure
# For parallel version (sciped for now)
# decomposePar
# sbatch -n 4 
# mpirun -np 4 pimpleFoam -parallel > log.pimpleFoam 
# reconstructPar

# One thread version
runApplication porousSimpleFoam | tee log logs/log_$(date '+%y-%m-%d_%X')

# Demo is stopped on this stop for now

# 6. Collect data
# Some paraview scripts

