#!/bin/bash

HERE=/home/vuranlab/cups-data

PID=`ps auxww | grep woofc-container | grep -v grep | awk '{print $2}'`
if ( test -z "$PID" ) ; then
	kill -9 `ps auxww | grep woofc-forker-helper | grep -v grep | awk '{print $2}'`	
	kill -9 `ps auxww | grep woofc-namespace-platform | grep -v grep | awk '{print $2}'`	
	cd $HERE
	$HERE/woofc-namespace-platform -b spawn >& $HERE/namespace.log &
	echo `/bin/date` "restarted namespace platform"
fi

