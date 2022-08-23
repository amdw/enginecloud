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

if [ -z $1 ]
then
    echo "No self-delete time specified: will not self-delete"
    exit 0
fi

INSTANCE_NAME=$(curl -s -X GET http://metadata.google.internal/computeMetadata/v1/instance/name -H 'Metadata-Flavor: Google' --fail-with-body)
INSTANCE_PROJECT=$(curl -s -X GET http://metadata.google.internal/computeMetadata/v1/project/project-id -H 'Metadata-Flavor: Google' --fail-with-body)
INSTANCE_ZONE=$(curl -s -X GET http://metadata.google.internal/computeMetadata/v1/instance/zone -H 'Metadata-Flavor: Google' --fail-with-body)

echo "Sleeping for $1 then will self-delete $INSTANCE_NAME in project $INSTANCE_PROJECT zone $INSTANCE_ZONE using gcloud"

sleep $1

echo "Self-deleting now."
gcloud compute instances delete $INSTANCE_NAME --zone=$INSTANCE_ZONE --project=$INSTANCE_PROJECT --quiet
