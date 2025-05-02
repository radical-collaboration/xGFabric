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
cd xGFabric/service
git checkout devel
pip install .

cat service.cfg
xgfabric-service.py service.cfg
```

Shell 2:
```sh
touch 'INPUT/test_1.dat'
# sleep ...
cat 'OUTPUT/test_1.dat.out'
```

