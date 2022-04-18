#!/bin/bash
# Copyright 2022 Andrew Medworth
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

if ! [[ $PWD == $HOME ]]
then
    echo "This script is intended to be run from the home directory on your VM."
    exit 1
fi

NVIDIA_OS=ubuntu2004
NVIDIA_ARCH=x86_64
# cuda 11.6 not yet supported on Google Cloud: https://cloud.google.com/compute/docs/troubleshooting/known-issues#nvidia-510
# However, the 510 driver seems to work even across a reboot, though the docs say it shouldn't...
CUDA_PACKAGE=cuda-11-5
CUDNN_VERSION=8.4.0.27
CUDNN_CUDA_VERSION=cuda11.6

LC0_GIT_BRANCH=release/0.28
# The network included with https://github.com/LeelaChessZero/lc0/releases/download/v0.28.2/lc0-v0.28.2-windows-gpu-nvidia-cuda.zip
LC0_NETWORK_HASH=65d1d197e81e221552b0803dd3623c738887dcb132e084fbab20f93deb66a0c0
LC0_NETWORK_FILE=752187.pb.gz

echo "Installing required packages..."
sudo apt-get update
sudo apt-get install -y unzip python3-pip build-essential g++ clang ninja-build zlib1g libgtest-dev
sudo pip3 install meson

# echo "Installing NVidia drivers..."
# curl https://raw.githubusercontent.com/GoogleCloudPlatform/compute-gpu-installation/main/linux/install_gpu_driver.py --output install_gpu_driver.py
# sudo python3 install_gpu_driver.py
# sudo nvidia-smi

echo "Adding NVidia package repository..."
wget https://developer.download.nvidia.com/compute/cuda/repos/${NVIDIA_OS}/${NVIDIA_ARCH}/cuda-${NVIDIA_OS}.pin
sudo mv cuda-${NVIDIA_OS}.pin /etc/apt/preferences.d/cuda-repository-pin-600
sudo apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/${NVIDIA_OS}/${NVIDIA_ARCH}/7fa2af80.pub
sudo add-apt-repository "deb https://developer.download.nvidia.com/compute/cuda/repos/${NVIDIA_OS}/${NVIDIA_ARCH}/ /"
sudo apt-get update

echo "Installing CUDA..."
# Instructions from https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html
sudo apt-get -y install $CUDA_PACKAGE
sudo nvidia-smi

echo "Installing libcudnn..."
# Instructions from https://docs.nvidia.com/deeplearning/cudnn/install-guide/index.html
sudo apt-get install libcudnn8=${CUDNN_VERSION}-1+${CUDNN_CUDA_VERSION}
sudo apt-get install libcudnn8-dev=${CUDNN_VERSION}-1+${CUDNN_CUDA_VERSION}

echo "Disabling graphical environment to save resources..."
sudo systemctl set-default multi-user

echo "Downloading Leela Chess Zero..."
git clone -b $LC0_GIT_BRANCH --recurse-submodules https://github.com/LeelaChessZero/lc0.git

echo "Downloading LC0 network..."
wget https://training.lczero.org/get_network?sha=${LC0_NETWORK_HASH} -O ${LC0_NETWORK_FILE}

echo "Building LC0..."
( cd lc0 && CC=clang CXX=clang++ ./build.sh | tee $HOME/build.log ) && cp ${LC0_NETWORK_FILE} lc0/build/release

echo "Complete. Try running lc0/build/release/lc0 benchmark."
echo "If all looks good, you can just use the engine - or create an image from it with create_image.sh."