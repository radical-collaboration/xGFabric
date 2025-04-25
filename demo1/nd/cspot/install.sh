#!/bin/bash

if [ conda list --name nd-xgfabric ]
then
    echo "already created fabric environment"
else
    echo "creating fabric environment"
    conda env create --file=environment.yml
fi

conda activate nd-xgfabric

# conda env update --file environment.yml --prune

git clone https://github.com/MAYHEM-Lab/cspot
cd cspot
git submodule update --init --recursive
mv deps/libzmq/CMakeLists.txt deps/libzmq/CMakeLists.orig.txt

sed 's/build the tests" ON/build the tests" OFF/' deps/libzmq/CMakeLists.orig.txt > deps/libzmq/CMakeLists.txt


# fix some files
line_to_prepend="#define _GNU_SOURCE"
file="deps/mio/mio.c"
sed -i "1i $line_to_prepend" "$file"

line_to_prepend="#include <sys/wait.h>"
file="apps/runs-test/cspot-runstat-multi-ns.c"
sed -i "1i $line_to_prepend" "$file"

line_to_prepend="#include <arpa/inet.h>"
file="apps/senspot/senspot.c"
sed -i "1i $line_to_prepend" "$file"

line_to_prepend="#include <arpa/inet.h>"
file="apps/senspot/senspot-put.c"
sed -i "1i $line_to_prepend" "$file"

content='
#include <stdlib.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "woofc.h"
#include "senspot.h"
int senspot_log(WOOF *wf, unsigned long seq_no, void *ptr)
{
	SENSPOT *spt = (SENSPOT *)ptr;
	time_t t = (time_t)spt->tv_sec;
	fprintf(stdout,"seq_no: %lu %s recv type %c from %s and timestamp %s\n",
			seq_no,
			WoofGetFileName(wf),
			spt->type,
			spt->ip_addr,
			ctime(&t));
	fflush(stdout);
	return(1);
}
'
file="apps/senspot/senspot_log.c"
echo "$content" > "$file"


content='
find_package(OpenSSL REQUIRED)

if(NOT OpenSSL_FOUND)
    message(FATAL_ERROR "OpenSSL not found.")
else()
    include_directories(${OpenSSL_INCLUDE_DIRS})
endif()

string(REPLACE ".so" ".a" OPENSSL_STATIC_LIBS "${OPENSSL_LIBRARIES}")

target_compile_options(woofc-container PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
target_compile_options(woofc-forker-helper PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
target_compile_options(woofc-mqtt-gateway PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
'
file="CMakeLists.txt"
echo "$content" >> "$file"


content='
target_compile_options(log-test-thread PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
target_compile_options(log-test        PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
'
file="src/CMakeLists.txt"
echo "$content" >> "$file"

content='
find_package(OpenSSL REQUIRED)
if(OPENSSL_FOUND)
  include_directories(${OPENSSL_INCLUDE_DIR})
else()
  message(FATAL_ERROR "OpenSSL library not found.")
endif()
message(STATUS "OpenSSL CFlags: ${OPENSSL_LIBRARIES}")
include_directories("./include" "../include" "../../src/include" "../src/include")
add_library(woof_caplets woofc-caplets.c)
target_link_libraries(woof_caplets PUBLIC woof)
target_include_directories(woof_caplets PRIVATE "." "../../include")
add_executable(woofc-init-principal woofc-init-principal.c)
target_link_libraries(woofc-init-principal PRIVATE woof_caplets woof crypto dl)
target_include_directories(woofc-init-principal PRIVATE "../include")
add_executable(woofc-print-cap woofc-print-cap.c)
target_link_libraries(woofc-print-cap PRIVATE woof_caplets woof crypto dl)
target_include_directories(woofc-print-cap PRIVATE "../include")
target_compile_options(woof_caplets PUBLIC "-I${OPENSSL_INCLUDE_DIR}")
target_compile_options(woofc-init-principal PUBLIC "-I${OPENSSL_INCLUDE_DIR}")
target_compile_options(woofc-print-cap PUBLIC "-I${OPENSSL_INCLUDE_DIR}")
'
file="src/caplets/CMakeLists.txt"
echo "$content" > "$file"

mkdir build
cd build/
source ~/.bashrc
conda activate nd-xgfabric

cmake -G Ninja -DCMAKE_INSTALL_PREFIX=$HOME/.local ..
ninja
ninja install


apptainer build cspot-docker-centos7.sif docker://racelab/cspot-docker-centos7

if ! [[ $LD_LIBRARY_PATH == *"$HOME/.local/lib"* ]]; then
    echo -e "if ! [[ \$LD_LIBRARY_PATH == *\"$HOME/.local/lib\"* ]]; then\nexport  LD_LIBRARY_PATH=\"\$LD_LIBRARY_PATH:$HOME/.local/lib\"\nfi" >> ~/.bashrc
    source ~/.bashrc
fi

HERE=`pwd`
content='
# >>> CSPOT initialize >>>
case ":$PATH:" in
    *:'$HERE'/bin:*)
        ;;

    *)
        export PATH='$HERE'/bin${PATH:+:${PATH}}
        ;;
esac

# <<< CSPOT initialize <<<'
file="$HOME/.bashrc"
echo "$content" >> "$file"
source ~/.bashrc
conda activate nd-xgfabric


cp ../SELF-TEST.sh ./bin
cd ./bin
./SELF-TEST.sh
