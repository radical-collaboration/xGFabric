#!/bin/bash
if conda env list | grep -q "nd-xgfabric"
then
    echo "already created service environment"
else
    echo "creating service environment"
    conda env create -f environment.yml
fi

conda init bash

source ~/.bashrc

conda activate nd-xgfabric

touch service.cfg

dir=`pwd`

echo "
{
    \"url\": \"tcp://*:10000-10200\",

    \"data\": {
        \"input\" : \"INPUT\",
        \"output\": \"OUTPUT\"
    },

    \"controller\": {
        \"description\": {
            \"resource\"  : \"local.localhost\",
            \"runtime\"   : 3600,
            \"nodes\"     : 1
        }
    },

    \"workload\": [
        {
            \"executable\": \"date\"
        },
        {
            \"executable\": \"cd $dir && sh submit.sh\",
            \"arguments\" : []
        },
        {
            \"executable\": \"date\"
        }
    ]
}" > service.cfg


python bin/xgfabric-service.py service.cfg