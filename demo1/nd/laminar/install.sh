#!/bin/bash
if conda env list | grep -q "nd-xgfabric"
then
    echo "already created fabric environment"
else
    echo "creating fabric environment"
    conda env create -f ../environment.yml
fi

conda activate nd-xgfabric

# conda env update --file environment.yml --prune

git clone https://github.com/MAYHEM-Lab/laminar
cd laminar


# ---------------------------------- change lines in the middle of a file -------------------------------------------------
INPUT_FILE="operation_system/src/operations/df_internal.c"
TMP_FILE="$(mktemp)"
sed "s|#include <woofc.h>|#include <$HOME/.local/include/woofc.h>|" "$INPUT_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$INPUT_FILE"

INPUT_FILE="operation_system/src/operations/riot_benchmark/bloom_filter.cpp"
TMP_FILE="$(mktemp)"
sed 's|        if (!filter.contains(hash)) {|        if (filter.find(hash) == filter.end()) {|' "$INPUT_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$INPUT_FILE"

INPUT_FILE="type_system/src/serialization/ts_serialization_util.c"
TMP_FILE="$(mktemp)"
sed "s|#include <woofc.h>|#include <$HOME/.local/include/woofc.h>|" "$INPUT_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$INPUT_FILE"
# ---------------------------------- change lines in the middle of a file -------------------------------------------------


# -------- replace file ---------
cp ../.CMakeLists.txt .
mv .CMakeLists.txt CMakeLists.txt
# -------- replace file ---------


# -------------- preprend lines to files --------------
line_to_prepend='#include <stdlib.h>\
#include <unistd.h>\
#include <sys/time.h>\
#include <fcntl.h>\
#include <sys/stat.h>\
#include <errno.h>'
file="type_system/extern/uuid/src/gen_uuid.c"
sed -i "1i $line_to_prepend" "$file"

line_to_prepend='#include "operations/df_arithmetic.h"'
file="operation_system/src/df_operation.c"
sed -i "1i $line_to_prepend" "$file"
# -------------- preprend lines to files --------------


# ----------------- append lines to file ----------------------
content='
include(CheckIncludeFile)
check_include_file("unistd.h" HAVE_UNISTD_H)
check_include_file("stdlib.h" HAVE_STDLIB_H)
check_include_file("sys/time.h" HAVE_SYS_TIME_H)'
echo "$content" >> 'type_system/extern/uuid/src/CMakeLists.txt'
# ----------------- append lines to file ----------------------


mkdir build
cd build/
source ~/.bashrc
conda activate nd-xgfabric


conda=`echo "$CONDA_PREFIX"`
cp "${HOME}/.local/lib64/libzmq.a" "${conda}/lib"

cmake -DCMAKE_INSTALL_PREFIX=$HOME/.local ..
make
