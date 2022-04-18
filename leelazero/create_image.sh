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

source leelazero/settings.sh

# The disk name should be the same as the instance name.
GCP_DISK_NAME=$GCP_INSTANCE_NAME
# Create a dated leela image
IMAGE_NAME="leela-$(date "+%Y%m%d")"

echo "Stopping the VM instance..."
gcloud compute instances stop $GCP_INSTANCE_NAME --zone $GCP_ZONE

# Not sure this next step is necessary, but the documentation says to do it:
# https://cloud.google.com/compute/docs/images/create-delete-deprecate-private-images
gcloud compute instances set-disk-auto-delete $GCP_INSTANCE_NAME \
    --no-auto-delete \
    --disk=$GCP_DISK_NAME \
    --zone $GCP_ZONE

echo "Creating image $IMAGE_NAME"
gcloud compute images create $IMAGE_NAME \
    --source-disk=$GCP_DISK_NAME \
    --source-disk-zone=$GCP_ZONE \
    --family=$GCP_CREATED_IMAGE_FAMILY

echo "Images now in your project in family ${GCP_CREATED_IMAGE_FAMILY}:"
gcloud compute images list --filter "family:${GCP_CREATED_IMAGE_FAMILY}" --project $GCP_PROJECT

echo "Image created. You can now delete the VM and disks if you wish:"
echo "gcloud compute instances delete $GCP_INSTANCE_NAME --zone $GCP_ZONE"
echo "gcloud compute disks delete $GCP_DISK_NAME --zone $GCP_ZONE"
