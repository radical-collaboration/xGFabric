The main CSPOT repo is
[https://github.com/MAYHEM-Lab/cspot](https://github.com/MAYHEM-Lab/cspot).

The main Laminar repo is
[https://github.com/MAYHEM-Lab/laminar](https://github.com/MAYHEM-Lab/laminar).

The script
````
collect_data.sh
````

should be run as a cron job on a 3 minute duty cycle from within the CSPOT
namespace where the CSPOT service is running.  The path to the namespace
should be set to the "HERE" variable in the script on the machine where it is
to be run (i.e. the head node of the cluster).

The script does not require special user privileges but it does require write
access to the CSPOT namespace directory.




## Steps for installing CSPOT

1. Make sure that you have Miniconda installed on your machine.

2. Run the install script with the command: `sh install.sh`

## Steps for running CSPOT

1. 