#!/bin/bash
set -e

echo "Installing CSPOT"

# Setup shell environment
source ~/.bashrc 2>/dev/null || true
eval "$(conda shell.bash hook)"
conda activate xgfabric

# Clean up old cspot directory if it exists
if [ -d "cspot" ]; then
    echo "CSPOT directory already exists, skipping clone..."
else
    # clone source and update submodules
    echo "Cloning CSPOT repository..."
    git clone https://github.com/MAYHEM-Lab/cspot
fi

cd cspot

echo "Checking out caplets branch..."
git checkout caplets 2>/dev/null || true
git checkout 61b662a76e21b34a4e9c6ed002b017888e287310 2>/dev/null || true

echo "Updating submodules..."
git submodule update --init --recursive 2>/dev/null || true

# Handle libzmq CMakeLists
if [ -f "deps/libzmq/CMakeLists.txt" ]; then
    mv deps/libzmq/CMakeLists.txt deps/libzmq/CMakeLists.orig.txt 2>/dev/null || true
    sed 's/build the tests" ON/build the tests" OFF/' deps/libzmq/CMakeLists.orig.txt > deps/libzmq/CMakeLists.txt 2>/dev/null || true
fi

# Create build directory if it doesn't exist
mkdir -p build
cd build

# Build the project
echo "Building CSPOT..."
cmake -G Ninja -DCMAKE_INSTALL_PREFIX=$HOME/.local .. 2>&1 | tail -20 || true
ninja 2>&1 | tail -20 || true
ninja install 2>&1 | tail -10 || true

# Update LD_LIBRARY_PATH
if ! [[ $LD_LIBRARY_PATH == *"$HOME/.local/lib"* ]]; then
    echo "Updating LD_LIBRARY_PATH in .bashrc..."
    echo -e "if ! [[ \$LD_LIBRARY_PATH == *\"$HOME/.local/lib\"* ]]; then\n  export LD_LIBRARY_PATH=\"\$LD_LIBRARY_PATH:$HOME/.local/lib\"\nfi" >> ~/.bashrc
fi

# Update PATH for CSPOT
echo "Updating PATH in .bashrc..."
if ! grep -q "CSPOT initialize" "$HOME/.bashrc"; then
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

# Reload bashrc to make senspot-get available
source ~/.bashrc 2>/dev/null || true

echo "CSPOT installation completed"
