#!/bin/bash

touch out.log

echo "Task started at [$(date '+%Y-%m-%d %H:%M:%S')]" >> out.log

source ./install.sh

# start the script
cd damBreak

sh ./Allrun

paraFoam -builtin

cd ..

echo "Task finished at [$(date '+%Y-%m-%d %H:%M:%S')]" >> out.log