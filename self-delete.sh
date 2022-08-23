#!/bin/bash

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
