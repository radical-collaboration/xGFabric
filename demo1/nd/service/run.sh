#!/bin/bash
if conda env list | grep -q "fabric-service"
then
    echo "already created service environment"
else
    echo "creating service environment"
    conda env create -f environment.yml
fi

conda activate fabric-service

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