#!/bin/bash
HERE=/home/vuranlab/cups-data
BIN=/home/vuranlab/bin
SRC="woof://169.231.230.76/sharedfs/unl-data/daviscupsout"
cd $HERE

if ( test -e "$HERE/windspeed-alert.lock" ) ; then
	echo `/bin/date` "another windspeed-alert.sh is running"
	exit 1
fi
$HERE/check-platform.sh

if ( test -e "$HERE/windspeed-alert.log" ) ; then
	LASTNO=`cat $HERE/windspeed-alert.log`
else
	LASTNO=999999
fi

LINE=`$BIN/senspot-get -W $SRC`
if ( test -z "$LINE" ) ; then
	echo `/bin/date` "no line from $SRC"
	exit 1
fi
FTEST=`echo $LINE | grep tcp`
if ( ! test -z "$FTEST" ) ; then
	echo `/bin/date` "$FTEST from $SRC"
	exit 1
fi
SEQNO=`echo $LINE | awk '{print $6}'`
if ( test -z "$SEQNO" ) ; then
	echo `/bin/date` "no seqno from $SRC"
	exit 1
fi

if ( test $LASTNO -eq $SEQNO ) ; then
	echo `/bin/date` "waiting for update of $SRC at $SEQNO"
	exit 0
fi

NEXTNO=$(($LASTNO+1))
while ( test $NEXTNO -lt $SEQNO ) ; do
	LINE1=`$BIN/senspot-get -W $SRC -S $NEXTNO`
	if ( test -z "$LINE1" ) ; then
		echo `/bin/date` "no line from $SRC at $NEXTNO"
		exit 1
	fi
	FTEST1=`echo $LINE1 | grep tcp`
	if ( ! test -z "$FTEST1" ) ; then
		echo `/bin/date` "$FTEST1 from $SRC at $NEXTNO"
		exit 1
	fi
	WINDSPEED1=`echo $LINE1 | awk -F ":" '{printf "%f",$4}'`
	if ( test -z "$WINDSPEED1" ) ; then
		echo `/bin/date` "no windpseed from $SRC at $NEXTNO"
		exit 1
	fi
	echo $WINDSPEED1 | $HERE/woof_change_body
	echo `/bin/date` "updated changepoint in $SRC at $NEXTNO"
	echo $NEXTNO > $HERE/windspeed-alert.log
	NEXTNO=$(($NEXTNO+1))
done
LINE=`$BIN/senspot-get -W $SRC -S $SEQNO`
if ( test -z "$LINE" ) ; then
	echo `/bin/date` "no line from $SRC at $SEQNO"
	exit 1
fi
FTEST=`echo $LINE | grep tcp`
if ( ! test -z "$FTEST" ) ; then
	echo `/bin/date` "$FTEST from $SRC at $SEQNO"
	exit 1
fi
WINDSPEED=`echo $LINE | awk -F ":" '{printf "%f",$4}'`
if ( test -z "$WINDSPEED" ) ; then
	echo `/bin/date` "no windpseed from $SRC at $SEQNO"
	exit 1
fi
echo $WINDSPEED | $HERE/woof_change_body
echo `/bin/date` "updated changepoint in $SRC at $SEQNO"
echo $SEQNO > $HERE/windspeed-alert.log



