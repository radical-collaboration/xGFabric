#!/bin/bash
conda env create --file=environment.yml
conda activate cspot

# conda env update --file environment.yml --prune

# wget https://github.com/ninja-build/ninja/releases/download/v1.10.2/ninja-linux.zip
# unzip ninja-linux.zip 
# mv ninja $HOME/.local/bin
# rm ninja-linux.zip

# wget https://github.com/Kitware/CMake/releases/download/v3.19.1/cmake-3.19.1-Linux-x86_64.sh
# chmod +x cmake-3.19.1-Linux-x86_64.sh 
# mkdir ~/.cmake
# ./cmake-3.19.1-Linux-x86_64.sh --skip-license --prefix=$HOME/.cmake

# yum -y localinstall https://download-ib01.fedoraproject.org/pub/epel/7/x86_64/Packages/c/czmq-3.0.2-3.el7.x86_64.rpm

# echo 'case ":$PATH:" in
#     *:/afs/crc.nd.edu/user/r/rhartung/.cmake/bin:*)
#         ;;

#     *)
#         export PATH=/afs/crc.nd.edu/user/r/rhartung/.cmake/bin${PATH:+:${PATH}}
#         ;;
# esac' >> ~/.bashrc


git clone https://github.com/MAYHEM-Lab/cspot
cd cspot
git submodule update --init --recursive
mv deps/libzmq/CMakeLists.txt deps/libzmq/CMakeLists.orig.txt

sed 's/build the tests" ON/build the tests" OFF/' deps/libzmq/CMakeLists.orig.txt > deps/libzmq/CMakeLists.txt


# wget https://github.com/openssl/openssl/releases/download/openssl-3.4.1/openssl-3.4.1.tar.gz
# tar -xvzf openssl-3.4.1.tar.gz
# cd openssl-3.4.1
# ./config --prefix=/usr/local/openssl --openssldir=/usr/local/openssl
# make
# make install


mkdir build
cd build/
source ~/.bashrc
conda activate cspot

export CPATH=$CONDA_PREFIX/include
export LIBRARY_PATH=$CONDA_PREFIX/lib
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
export CXXFLAGS="-std=c++17"
export CXXFLAGS="-D_GLIBCXX_USE_CXX11_ABI=0"
export CC=$(which x86_64-conda-linux-gnu-cc)
export CXX=$(which x86_64-conda-linux-gnu-c++)
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH


cmake -G Ninja ..
ninja
ninja install


#scl enable devtoolset-9 ./helper.sh
docker pull racelab/cspot-docker-centos7
docker tag racelab/cspot-docker-centos7 cspot-docker-centos7

if ! [[ $LD_LIBRARY_PATH == *"/usr/local/lib"* ]]; then
    echo -e "if ! [[ \$LD_LIBRARY_PATH == *\"/usr/local/lib\"* ]]; then\nexport  LD_LIBRARY_PATH=\"\$LD_LIBRARY_PATH:/usr/local/lib\"\nfi" >> ~/.bashrc
    source ~/.bashrc
fi
cp ../SELF-TEST.sh ./bin
cd ./bin
./SELF-TEST.sh




# -- Install:
# --   Install prefix    :/usr/local
# -- 
# -- ************************* Options ***************************
# -- Options:
# --   Use the Draft API (default = yes):
# --   -DENABLE-DRAFTS=[yes|no]
# -- 
# -- *************************************************************
# -- Configuration complete! Now procced with:
# --   'make'                 compile the project
# --   'make test'            run the project's selftest
# --   'make install'         install the project to /usr/local
# -- 
# -- Further options are:
# --   'ctest -V              run test with verbose logging
# --   'ctest -R <test_name>' run a specific test
# --   'ctest -T memcheck'    run the project's selftest with
# --                          valgrind to check for memory leaks
