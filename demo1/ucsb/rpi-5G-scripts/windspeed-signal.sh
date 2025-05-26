#/bin/bash
#
# this runsthe Laminar body on the recive side and pushes the data into a woof

echo $$ "bash PID"
cd /sharedfs/unl-data
while [ 1 ] ; do
        echo `/bin/date` "calling woof_change_body"
        VALUE=`./woof_change_body | grep "signal" | awk '{print $6}'`
        if ( ! test -z "$VALUE" ) ; then
                echo $VALUE | ./senspot-put -W woof://169.231.230.76/sharedfs/unl-data/windspeed-signal -T d
                echo `/bin/date` "SIGNAL:" $VALUE
        else
                echo `/bin/date` "no value"
        fi
done


