EC_HOME=$HOME/enginecloud
SSH_USER=$USER

GCP_PROJECT=
GCP_ZONE=
GCP_MACHINE_TYPE=
ACCELERATOR_PARAMS=
GCP_INSTANCE_NAME=leelazero
# Some software install steps could probably be skipped if we used a "deep learning image":
# https://cloud.google.com/deep-learning-vm/docs/images
# However I wanted to show how to get things working starting from a standard Linux image.
GCP_BASE_IMAGE_PROJECT=ubuntu-os-cloud
GCP_BASE_IMAGE_FAMILY=ubuntu-2004-lts

GCP_CREATED_IMAGE_FAMILY=leelazero
