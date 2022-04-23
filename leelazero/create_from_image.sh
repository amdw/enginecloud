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

if ! [[ -f leelazero/settings.sh ]]
then
	echo "Could not find settings file: make sure you are running from the root of the repo"
	echo "and have copied leelazero/settings_template.sh to leelazero/settings.sh and filled it in."
	exit 1
fi

source leelazero/settings.sh

if ! [[ -e $EC_HOME ]]; then mkdir $EC_HOME; fi

leelazero/build_client.sh

gcloud compute instances create $GCP_INSTANCE_NAME \
    --project $GCP_PROJECT \
    --zone $GCP_ZONE \
    --machine-type $GCP_MACHINE_TYPE \
    --accelerator $ACCELERATOR_PARAMS \
    --image-family $GCP_CREATED_IMAGE_FAMILY \
    --boot-disk-size 200GB \
    --maintenance-policy=TERMINATE \
    --restart-on-failure

echo "Created virtual machine - it should now be using billable resources."
