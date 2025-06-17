#!/bin/bash
destination="$1"
pvpython --force-offscreen-rendering render_foam.py $destination
# xvfb-run -a -s "-screen 0 3840x2160x24" pvpython render_foam.py $destination

python3 create_gif.py $destination