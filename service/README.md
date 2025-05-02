# xGFabric Service Endpoint

Shell 1:
```sh
python3 -v venv ve3
. ve3/in/activate

git clone git@github.com:radical-cybertools/workflow-mini-apps.git
cd workflow-mini-apps
git checkout dev_xgfabric
pip install wfMiniAPI
cd ..


git clone git@github.com:radical-cybertools/xGFabric.git
./bin/xgfabric-service.py
```

Shell 2:
```sh
cd INPUT/
touch 'new_data.dat'
ls -l 'new_data.dat.done'
cd ../OUTPUT/
ls -l 'new_data.dat.out'
```

