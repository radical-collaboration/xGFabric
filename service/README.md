# xGFabric Service Endpoint

Shell 1:
```sh
python3 -v venv ve3
. ve3/in/activate
pip install .
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

