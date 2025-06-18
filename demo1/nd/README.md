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
In the OpenFOAM folder, you can test OpenFOAM by typing: 
```
cd OpenFOAM/parallel_test
sh runme.sh
```