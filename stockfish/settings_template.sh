EC_HOME=$HOME/enginecloud
SSH_USER=$USER
STOCKFISH_VERSION="stockfish_15.1_linux_x64_bmi2"
STOCKFISH_BINARY="stockfish_15.1_x64_bmi2"

GCP_PROJECT=
GCP_ZONE=
GCP_MACHINE_TYPE=
# Newer Stockfish binaries require newer libc versions hence relatively recent Ubuntu
GCP_IMAGE_PROJECT=ubuntu-os-cloud
GCP_IMAGE_FAMILY=ubuntu-2204-lts
GCP_INSTANCE_NAME=stockfish

# Delay after startup beyond which the VM should delete itself.
# Set this to the maximum time you want to use the VM for:
# this protects against accidentally forgetting to delete it.
# Do not set this if you intend to store things on the VM which you want to keep!
# Default is 1 hour.
SELF_DELETE_TIME=3600
