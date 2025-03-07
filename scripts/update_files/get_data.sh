#!/bin/bash

# get data following Rich instruction
b=$(/sharedfs/cups-data/senspot-get -W woof://169.231.230.76/sharedfs/cups-data/daviscupsout)
vals=$(awk -F" " '{print $1}' <<< "$b")
windspeed=$(awk -F":" '{print $6}' <<< "$vals")
winddir=$(awk -F":" '{print $7}' <<< "$vals")
# Split velocity and direction on componets x and y, or get components if there is any


# Update files
python3 update_files/unzip_and_update.py $windspeed $winddir --file cfd_test.zip


# cd testfstructure/small_structure
# ./Allrun