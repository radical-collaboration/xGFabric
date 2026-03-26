#!/bin/bash
job_id="${echo "Your job 737147 ('pinn_train') has been submitted" | awk '{print $3}'

echo "$job_id"