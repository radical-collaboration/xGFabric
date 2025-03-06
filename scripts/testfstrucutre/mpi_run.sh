#!/bin/sh
mpirun -np 4 pimpleFoam -parallel > log.pimpleFoam &
