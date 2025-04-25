#!/bin/bash
BIN="/afs/crc.nd.edu/user/r/rhartung/Documents/xGFabric/xGFabric/demo1/nd/cspot/cspot/build/bin"
HERE=`pwd`
LOCALWOOF="woof://127.0.0.1$HERE/daviscupsout"
DATAWOOF="woof://169.231.230.76/sharedfs/unl-data/daviscupsout"
LINE=`$BIN/senspot-get -W $DATAWOOF`
DATA=`echo $LINE | awk '{printf "%s",$1}'`
SEQNO=`echo $LINE | awk '{print $6}'`
if ( ! test -e "$HERE/daviscupsout.last" ) ; then
        $BIN/senspot-init -W $HERE/daviscupsout -s 10000
        echo $SEQNO > $HERE/daviscupsout.last
        echo -n $DATA | sed 's/\n//g' | $BIN/senspot-put -W $LOCALWOOF -T s
        exit 0
fi
LASTSEQNO=`cat $HERE/daviscupsout.last`
if ( test $LASTSEQNO -eq $SEQNO ) then
        exit 0
fi
NEXT=$(($LASTSEQNO+1))
while ( test $NEXT -lt $SEQNO ) ; do
        LINE1=`$HERE/senspot-get -W $DATAWOOF -S $NEXT`
        DATA1=`echo $LINE1 | awk '{printf "%s",$1}'`
        echo -n $DATA1 | sed 's/\n//g' | $BIN/senspot-put -W $LOCALWOOF -T s
        NEXT=$(($NEXT+1))
done
echo -n $DATA | sed 's/\n//g' | $BIN/senspot-put -W $LOCALWOOF -T s
echo $SEQNO > $HERE/daviscupsout.last