#!/bin/bash
BIN=/home/vuranlab/bin
HERE=/home/vuranlab/cups-data

cd $HERE

if ( test -e "$HERE/relay.lock" ) ; then
	echo `/bin/date` "anopther relay running"
	exit 1
fi

touch $HERE/relay.lock

SRC="woof://128.111.45.61/davisstations/daviscupsout"
DST="woof://169.231.230.76/sharedfs/unl-data/daviscupsout"

LINE=`$BIN/senspot-get -W $SRC | sed 's/\n//g'`
STEST=`echo $LINE | grep tcp`
if ( ! test -z "$STEST" ) ; then
	rm -f $HERE/relay.lock
	exit 1
fi
if ( test -z "$LINE" ) ; then
	rm -f $HERE/relay.lock
	exit 1
fi
SEQNO=`echo $LINE | awk '{print $6}'`
if ( ! test -e "$HERE/relay.log" ) ; then
	echo -n $LINE | awk '{printf "%s",$1}' | sed 's/\n//' | $BIN/senspot-put -W $DST -T s
	echo $SEQNO > $HERE/relay.log
else
	LASTNO=`cat $HERE/relay.log`
	FTEST=`echo $LASTNO | grep tcp`
	if ( ! test -z "$FTEST" ) ; then
		rm -f $HERE/relay.lock
		rm -f $HERE/relay.log
		exit 1
	fi
	if ( test $LASTNO -eq $SEQNO ) ; then
		rm -f $HERE/relay.lock
		exit 0
	fi
	NEXTNO=$(($LASTNO+1))
	while ( test $NEXTNO -lt $SEQNO ) ; do
		LINE1=`$BIN/senspot-get -W $SRC -S $NEXTNO | sed 's/\n//g'`
		S1TEST=`echo $LINE1 | grep tcp`
		if ( ! test -z "$S1TEST" ) ; then
			rm -f $HERE/relay.lock
			exit 1
		fi
		if ( ! test -z "$LINE1" ) ; then
			echo -n $LINE1 | awk '{printf "%s",$1}' | sed 's/\n//g' | $BIN/senspot-put -W $DST -T s
echo "updating" $NEXTNO
			echo $NEXTNO > $HERE/relay.log
			WINDSPEED=`echo -n $LINE1 | awk '{printf "%s",$1}' | awk -F ':' '{print $4}'`
#			if ( ! test -z "$WINDSPEED" ) ; then
#				echo $WINDSPEED | $HERE/woof_change_body &>> $HERE/wf.log
#			fi
			NEXTNO=$(($NEXTNO+1))
		else
			rm -f $HERE/relay.lock
			exit 1
		fi
	done
	echo -n $LINE | awk '{printf "%s",$1}' | sed 's/\n//g' | $BIN/senspot-put -W $DST -T s
echo "updating" $SEQNO
	echo $SEQNO > $HERE/relay.log
	WINDSPEED=`echo -n $LINE | awk '{printf "%s",$1}' | awk -F ':' '{print $4}'`
#	if ( ! test -z "$WINDSPEED" ) ; then
#		echo $WINDSPEED | $HERE/woof_change_body &>> $HERE/wf.log
#	fi
fi

rm -f $HERE/relay.lock

