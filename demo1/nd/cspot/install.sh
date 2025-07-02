#!/bin/bash
check_dir_exists (){
    if [ -d "$1/cspot" ]; then
        printf "Cannot install CSPOT at $install_location/.cspot. Directory already exists. Would you like to install CSPOT in a different location?\n\n==> Install location (leave blank to exit)\n==> "
        read new_location

        if [ -z "$new_location" ]; then
            exit 0
        fi

        install_location=$new_location
        check_dir_exists "$install_location"
    fi
}

printf "Where would you like CSPOT to be installed?\n\n==> The default location is \$HOME/cspot. Leave blank for default.\n==> "

read install_location

if [ -z "$install_location" ]; then
    install_location="$HOME"
elif [[ "$install_location" == "." ]]; then
    install_location=`pwd`
fi

check_dir_exists "$install_location"

source ~/.bashrc

echo "Installing CSPOT to $install_location/cspot"

cd "$install_location"

# activate environment
source ~/.bashrc
conda activate xgfabric 

# clone source and update submodules
git clone https://github.com/MAYHEM-Lab/cspot
cd cspot
git checkout caplets
git checkout 61b662a76e21b34a4e9c6ed002b017888e287310

git submodule update --init --recursive
mv deps/libzmq/CMakeLists.txt deps/libzmq/CMakeLists.orig.txt

sed 's/build the tests" ON/build the tests" OFF/' deps/libzmq/CMakeLists.orig.txt > deps/libzmq/CMakeLists.txt


#------------- Prepend lines ------------------
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
#------------- Prepend lines ------------------


#--------------------------------- Overwrite file --------------------------------
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

content='find_package(OpenSSL REQUIRED)
if(OPENSSL_FOUND)
  include_directories(${OPENSSL_INCLUDE_DIR})
else()
  message(FATAL_ERROR "OpenSSL library not found.")
endif()
message(STATUS "OpenSSL CFlags: ${OPENSSL_LIBRARIES}")
include_directories("./include" "../include" "../../src/include" "../src/include")
add_library(woof_caplets woofc-caplets.c woofc-keychain.c)
target_link_libraries(woof_caplets PUBLIC woof)
target_include_directories(woof_caplets PRIVATE "." "../../include")
add_executable(woofc-init-principal woofc-init-principal.c)
target_link_libraries(woofc-init-principal PRIVATE woof_caplets woof crypto dl pthread)
target_include_directories(woofc-init-principal PRIVATE ../include)
add_executable(woofc-print-cap woofc-print-cap.c)
target_link_libraries(woofc-print-cap PRIVATE woof_caplets woof crypto dl pthread)
target_include_directories(woofc-print-cap PRIVATE ../include)
target_compile_options(woof_caplets PUBLIC "-I${OPENSSL_INCLUDE_DIR}")
target_compile_options(woofc-init-principal PUBLIC "-I${OPENSSL_INCLUDE_DIR}")
target_compile_options(woofc-print-cap PUBLIC "-I${OPENSSL_INCLUDE_DIR}")'
file="src/caplets/CMakeLists.txt"
echo "$content" > "$file"
#--------------------------------- Overwrite file --------------------------------


#--------------------------------- Add lines to end of file ------------------------------------------
content='find_package(OpenSSL REQUIRED)

if(NOT OpenSSL_FOUND)
    message(FATAL_ERROR "OpenSSL not found.")
else()
    include_directories(${OpenSSL_INCLUDE_DIRS})
endif()

# string(REPLACE ".so" ".a" OPENSSL_STATIC_LIBS "${OPENSSL_LIBRARIES}")

target_compile_options(woofc-container PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
target_compile_options(woofc-forker-helper PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
target_compile_options(woofc-mqtt-gateway PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
'
file="CMakeLists.txt"
echo "$content" >> "$file"


content='target_compile_options(log-test-thread PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
target_compile_options(log-test PUBLIC "-I${OPENSSL_INCLUDE_DIR} -I${OPENSSL_STATIC_LIBS}")
'
file="src/CMakeLists.txt"
echo "$content" >> "$file"

content='target_compile_options(woof_cmq_net PUBLIC "-I../../caplets/woofc-keychain.h")'
file="src/net/cmq/CMakeLists.txt"
echo "$content" >> "$file"

content='target_compile_options(woof_zmq_net PUBLIC "-I../../caplets/woofc-keychain.h")'
file="src/net/zmq/CMakeLists.txt"
echo "$content" >> "$file"

#--------------------------------- Add lines to end of file ------------------------------------------

# ---------------------- change lines in the middle of a file -----------------------------
INPUT_FILE="src/net/zmq/client.cpp"
TMP_FILE="$(mktemp)"
sed '/#include "woofc-caplets.h"/a #include "woofc-keychain.h"' "$INPUT_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$INPUT_FILE"

INPUT_FILE="src/net/cmq/client.cpp"
TMP_FILE="$(mktemp)"
sed '/#include "woofc-caplets.h"/a #include "woofc-keychain.h"' "$INPUT_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$INPUT_FILE"

INPUT_FILE="src/caplets/woofc-keychain.c"
TMP_FILE="$(mktemp)"
sed '/#include "woofc-caplets.h"/a #include "woofc-keychain.h"' "$INPUT_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$INPUT_FILE"

INPUT_FILE="src/include/debug.h"
TMP_FILE="$(mktemp)"
sed "s|//#define QUIET|#define QUIET|" "$INPUT_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$INPUT_FILE"

INPUT_FILE="src/include/debug.h"
TMP_FILE="$(mktemp)"
sed 's|^#define DEBUG$|// #define DEBUG|' "$INPUT_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$INPUT_FILE"
# ---------------------- change lines in the middle of a file -----------------------------


# strip debug info off of static library files. This was required for Rocky Linux v8.10 (Purdue's ANVIL system)
conda_loc=`echo $CONDA_PREFIX`
strip --strip-debug $conda_loc/lib/gcc/x86_64-conda-linux-gnu/14.2.0/lib*.a

# create the build folder
mkdir build
cd build/

# activate the conda environment again
source ~/.bashrc
conda activate xgfabric

# build the project
cmake -G Ninja -DCMAKE_INSTALL_PREFIX=$HOME/.local ..
ninja
ninja install

# add the following to .bashrc
if ! [[ $LD_LIBRARY_PATH == *"$HOME/.local/lib"* ]]; then
    echo -e "if ! [[ \$LD_LIBRARY_PATH == *\"$HOME/.local/lib\"* ]]; then\nexport  LD_LIBRARY_PATH=\"\$LD_LIBRARY_PATH:$HOME/.local/lib\"\nfi" >> ~/.bashrc
    source ~/.bashrc
fi

# check if it's already there
if grep -Fxq "# >>> CSPOT initialize >>>" "$HOME/.bashrc"; then
    echo "CSPOT block already present in .bashrc"
else
    echo "Appending CSPOT block to .bashrc"
    # initialize cspot by putting it in .bashrc
    HERE=$(pwd)
    echo "# >>> CSPOT initialize >>>
case \":\$PATH:\" in
    *:$HERE/bin:*)
        ;;
    *)
        export PATH=$HERE/bin\${PATH:+:\${PATH}}
        ;;
esac

# <<< CSPOT initialize <<<" >> "$HOME/.bashrc"
fi

echo "Finished installing CSPOT"
source ~/.bashrc