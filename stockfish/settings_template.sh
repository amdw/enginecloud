EC_HOME=$HOME/enginecloud
SSH_USER=$USER
STOCKFISH_URL="https://github.com/official-stockfish/Stockfish/releases/download/sf_16/stockfish-ubuntu-x86-64-avx2.tar"
STOCKFISH_BINARY_PATH="stockfish/stockfish-ubuntu-x86-64-avx2"

GCP_PROJECT=
GCP_ZONE=
GCP_MACHINE_TYPE=
# Newer Stockfish binaries require newer libc versions hence relatively recent Ubuntu
GCP_IMAGE_PROJECT=ubuntu-os-cloud
GCP_IMAGE_FAMILY=ubuntu-2204-lts
GCP_INSTANCE_NAME=stockfish
# See https://cloud.google.com/compute/docs/instances/spot
PROVISIONING_MODEL=SPOT

# Delay after which the VM should delete itself.
# Set this to the maximum time you want to use the VM for:
# this protects against accidentally forgetting to delete it.
# Do not set this if you intend to store things on the VM which you want to keep!
# For possible values see https://cloud.google.com/compute/docs/instances/limit-vm-runtime
MAX_RUN_DURATION=1h
