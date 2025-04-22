#!/bin/bash

HERE=`pwd`
DATAWOOF="woof://169.231.230.76/sharedfs/unl-data/daviscupsout"

while [ 1 ] ; do
	LINE=`$HERE/senspot-get -W $DATAWOOF`
	SEQNO=`echo $LINE | awk '{print $6}'`
	if ( ! test -e "/tmp/weather-change.log" ) ; then
		echo $SEQNO > /tmp/weather-change.log
		LASTSEQNO=9999999
	else
		LASTSEQNO=`cat /tmp/weather-change.log`
	fi
	if ( test $LASTSEQNO -eq $SEQNO ) ; then
		echo "waiting for update"
		sleep 30
		continue
	fi
	NEXTSEQNO=$(($LASTSEQNO+1))
	while ( test $NEXTSEQNO -lt $SEQNO ) ; do
		LINE1=`$HERE/senspot-get -W $DATAWOOF -S $NEXTSEQNO`
		if ( test -z "$LINE1" ) ; then
			exit 1
		fi
		WINDSPEED=`echo $LINE1 | awk -F ':' '{print $4}'`
		echo $WINDSPEED | $HERE/woof_change_body
		echo $NEXTSEQNO > /tmp/weather-change.log
		NEXTSEQNO=$(($NEXTSEQNO+1))
	done
	WINDSPEED=`echo $LINE | awk -F ':' '{print $4}'`
	echo $WINDSPEED | $HERE/woof_change_body
	echo $SEQNO > /tmp/weather-change.log
	sleep 180
done

