## Installation

### Miniconda
1. Make sure that you have [Miniconda3](https://www.anaconda.com/docs/getting-started/miniconda/install) installed on you machine.
2. Run the following command to make sure that you have the xGFabric conda environment.
```
conda env create -f environment.yml
```

### CSPOT
1. Run the following commands to install and add CSPOT to your machine:
```
cd cspot
sh install.sh
```


## Running OpenFOAM
In the OpenFOAM folder, there are two directories. The testing directory was for testing OpenFOAM on the ND cluster. The other directory (parallel_test) is the portable version. To test the portable version, run the commands below. This will open up an interactive prompt which will ask which cluster you are running on, the number of threads you would like, and how many iterations of computation you would like to calculate.

Note: In order to produce the output GIF, you must have a display environment available on your command line. If you are accessing the cluster via SSH, then you would use the "-Y" flag when connecting. EX: `ssh -Y user@cluster.edu`
```
cd OpenFOAM/parallel_test
sh runme.sh
```