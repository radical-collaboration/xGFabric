#!/bin/bash

HERE=/sharedfs/cups-data

LINE=`$HERE/senspot-get -W woof://128.111.45.61/davisstations/daviscupsout`

DATA=`echo $LINE | awk '{printf "%s",$1}'`
SEQNO=`echo $LINE | awk '{print $6}'`

if ( ! test -e "$HERE/daviscupsout.last" ) ; then
        $HERE/senspot-init -W daviscupsout -s 10000
        echo $SEQNO > $HERE/daviscupsout.last
        echo -n $DATA | sed 's/\n//g' | $HERE/senspot-put -W woof://169.231.230.76$HERE/daviscupsout -T s
        exit 0
fi

LASTSEQNO=`cat $HERE/daviscupsout.last`
if ( test $LASTSEQNO -eq $SEQNO ) then
        exit 0
fi
NEXT=$(($LASTSEQNO+1))


while ( test $NEXT -lt $SEQNO ) ; do
        LINE1=`$HERE/senspot-get -W woof://128.111.45.61/davisstations/daviscupsout -S $NEXT`
        DATA1=`echo $LINE1 | awk '{printf "%s",$1}'`
        echo -n $DATA1 | sed 's/\n//g' | $HERE/senspot-put -W woof://169.231.230.76$HERE/daviscupsout -T s
        NEXT=$(($NEXT+1))
done

echo -n $DATA | sed 's/\n//g' | $HERE/senspot-put -W woof://169.231.230.76$HERE/daviscupsout -T s
echo $SEQNO > $HERE/daviscupsout.last

