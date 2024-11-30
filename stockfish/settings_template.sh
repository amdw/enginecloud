EC_HOME=$HOME/enginecloud
SSH_USER=$USER

# See https://stockfishchess.org/download/linux/ for Stockfish binaries optimised for different platforms.

# Works on c3d machine family but not n2d.
STOCKFISH_URL="https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-vnni512.tar"
STOCKFISH_BINARY_PATH="stockfish/stockfish-ubuntu-x86-64-vnni512"

# Fallback that works on n2d machine family.
# STOCKFISH_URL="https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-bmi2.tar"
# STOCKFISH_BINARY_PATH="stockfish/stockfish-ubuntu-x86-64-bmi2"

GCP_PROJECT=
GCP_ZONE=
# For available machine types in a zone, run:
# gcloud compute machine-types list --filter="zone=(${GCP_ZONE})"
# See also https://cloud.google.com/compute/docs/machine-resource
GCP_MACHINE_TYPE=

# Newer Stockfish binaries require newer libc versions hence relatively recent Ubuntu
# gcloud compute images list | grep ubuntu
GCP_IMAGE_PROJECT=ubuntu-os-cloud
GCP_IMAGE_FAMILY=ubuntu-2404-lts-amd64
GCP_INSTANCE_NAME=stockfish
# See https://cloud.google.com/compute/docs/instances/spot
PROVISIONING_MODEL=SPOT

# Delay after which the VM should delete itself.
# Set this to the maximum time you want to use the VM for:
# this protects against accidentally forgetting to delete it.
# Do not set this if you intend to store things on the VM which you want to keep!
# For possible values see https://cloud.google.com/compute/docs/instances/limit-vm-runtime
MAX_RUN_DURATION=1h
