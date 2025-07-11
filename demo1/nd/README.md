# How to use these scripts

## Part One: Installation

### Automatic Installation

The shell file, `install.sh`, contains a script that should automatically install the required dependencies to your machine. It will detect if you have Miniconda installed, if you have the fabric environment, and if OpenFOAM can run on your system.

Note: In the event that it doesn't work, please either rerun the file, or try following the manual steps below. It has been successfully tested and run on the Notre Dame, Texas Stampede3, and Purdue ANVIL clusters.


### Manual Installation

#### Miniconda
1. Make sure that you have [Miniconda3](https://www.anaconda.com/docs/getting-started/miniconda/install) installed on you machine. You can check by running the following command:

```
which conda
```

If this fails, then please either follow the instructions from the link above, or run the following code if you are on Linux:

```
mkdir -p ~/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
rm ~/miniconda3/miniconda.sh
source ~/miniconda3/bin/activate
conda init bash
source ~/.bashrc
```


2. Run the following command to make sure that you have the xGFabric conda environment.
```
conda env list | grep -q "xgfabric"
```
If nothing appears, then you need to install the conda environment by running the following command


```
conda env create -f environment.yml
```

#### CSPOT
1. Run the following commands to install and add CSPOT to your machine.
```
cd cspot
sh install.sh
```

2. You can verify whether you have CSPOT by running the following command:
```
which senspot-get
```

If this fails, then either restart your terminal or try reinstalling CSPOT


#### OpenFOAM and ParaView
1. Most clusters come preinstalled with both OpenFOAM and ParaView through the modules command. To see the list of available modules on your system, please run the following command:
```
module avail
```

This should display a long list of all the available modules. If you do not see OpenFOAM or ParaView, then you may need to manually install and compile them.

2. To load the modules, please run the following command (fill in with the correct version number of OpenFOAM and ParaView):
```
module load OpenFOAM/###
module load ParaView/###
```

Note: Most of the time, you will need to load additional dependencies first. The system should tell you which are required, but if it does not, then you may need to run the following command (fill in with the correct version number of OpenFOAM and ParaView):
```
module spider OpenFOAM/###
module spider ParaView/###
```


## Part Two: Running OpenFOAM

### Authenticating the CSPOT request

The `senspot-get` command requires the user to authenticate their request before it will return any data. If you do not have the capabilities.yaml file in your home directory, then please do the following:

    1. Create a folder named .cspot in your home directory ($HOME/).
    2. Create or copy over the capabilities.yaml file and place it in the .cspot folder.
    3. Run 'chmod 700' on the .cspot folder.
    4. Run 'chmod 600' on the capabilities.yaml file.

If you do not have access a capabilities.yaml file, then please contact Rich Wolski at rich@cs.ucsb.edu or visit his website at https://sites.cs.ucsb.edu/~rich/ to find his contact information.


### Start OpenFOAM
There are two ways that you can initiate an OpenFOAM job.

1. You can run the `runme.sh` file with no command line arguments. This will open up an interactive prompt which will ask which cluster you are running on, the number of threads you would like, etc.

2. You can run the `runme.sh` with command line arguments. This is mainly used for submitting multiple jobs at the same time. You can run `sh runme.sh --help` to see the full command usage. The following is an example of what a typical submission would look like:
```
sh runme.sh -c=2 -t=32 -s=50 -r=false -b=true
```
Explanation: run on cluster number 2 (Note Dame) with 32 threads for 50 seconds/iteration, do not render the output, and run the task in the background (does not display the output of the task while it's running)


### NOTE:
If you want to render the output, then you must have a display environment available on your command line. If you are accessing the cluster via SSH, then you would use the "-Y" flag when connecting. EX: `ssh -Y user@cluster.edu`
