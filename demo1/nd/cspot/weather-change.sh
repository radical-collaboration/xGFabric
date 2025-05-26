#!/bin/bash
DATAWOOF="woof://169.231.230.76/sharedfs/unl-data/daviscupsout"

while [ 1 ] ; do
	LINE=`senspot-get -W $DATAWOOF`
	SEQNO=`echo $LINE | awk '{print $6}'`
	if ( ! test -e "data/seq_num.log" ) ; then
		echo "$SEQNO" > data/seq_num.log
		LASTSEQNO=9999999
	else
		LASTSEQNO=`cat data/seq_num.log`
	fi
	if ( test "$LASTSEQNO" -eq "$SEQNO" ) ; then
		echo "waiting for update"
		sleep 30
		continue
	fi
	NEXTSEQNO=$(($LASTSEQNO+1))
	while ( test "$NEXTSEQNO" -lt "$SEQNO" ) ; do
		LINE1=`senspot-get -W $DATAWOOF -S $NEXTSEQNO`
		if ( test -z "$LINE1" ) ; then
			exit 1
		fi
		WINDSPEED=`echo $LINE1 | awk -F ':' '{print $4}'`
		echo $WINDSPEED >> data/windspeed.txt
		python process_data.py $LINE1
		echo $NEXTSEQNO > data/seq_num.log
		NEXTSEQNO=$(($NEXTSEQNO+1))
	done
	WINDSPEED=`echo $LINE | awk -F ':' '{print $4}'`
	echo $WINDSPEED >> data/windspeed.txt
	python process_data.py $LINE
	echo $SEQNO > data/seq_num.log
	sleep 180
done