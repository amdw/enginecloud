#!/bin/bash
# Copyright 2022-2024 Andrew Medworth
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

if ! [[ -f stockfish/settings.sh ]]
then
	echo "Could not find settings file: make sure you are running from the root of the repo"
	echo "and have copied stockfish/settings_template.sh to stockfish/settings.sh and filled it in."
	exit 1
fi

source stockfish/settings.sh

if ! [[ -e $EC_HOME ]]; then mkdir $EC_HOME; fi

# We will create a symlink on the VM at this location pointing to the Stockfish binary
STOCKFISH_BINARY_LINK="/tmp/stockfish"

cat > ${EC_HOME}/run_stockfish.go <<EOF
package main

import (
	"log"
	"os"
	"os/exec"
)

func main() {
	cmd := exec.Command(
		"`which gcloud`", "compute", "ssh",
		"--zone", "${GCP_ZONE}",
		"${GCP_INSTANCE_NAME}", "--project", "${GCP_PROJECT}",
		\`--command="${STOCKFISH_BINARY_LINK}"\`,
		"--quiet")
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	err := cmd.Run()
	if err != nil {
		if err, ok := err.(*exec.ExitError); ok {
			log.Printf("SSH command exited with status %d", err.ExitCode())
			os.Exit(err.ExitCode())
		}
		log.Fatalf("Non-exit error from command execution: %s", err)
	}
}
EOF
( cd $EC_HOME && go build run_stockfish.go ) && echo "Built $EC_HOME/run_stockfish"

if [ ! -z $MAX_RUN_DURATION ]; then
	MAX_RUN_DURATION_FLAGS="--max-run-duration $MAX_RUN_DURATION --instance-termination-action DELETE"
fi

STOCKFISH_EXT="${STOCKFISH_URL##*.}"
STOCKFISH_DOWNLOAD_TO="/tmp/stockfish.$STOCKFISH_EXT"
STOCKFISH_EXTRACT_DIR=/tmp/sfextract
case $STOCKFISH_EXT in
	"zip") STOCKFISH_EXTRACT_COMMAND="unzip $STOCKFISH_DOWNLOAD_TO -d $STOCKFISH_EXTRACT_DIR" ;;
	"tar") STOCKFISH_EXTRACT_COMMAND="mkdir -p $STOCKFISH_EXTRACT_DIR && tar -xf $STOCKFISH_DOWNLOAD_TO -C $STOCKFISH_EXTRACT_DIR" ;;
	*) echo "Unsupported file type $STOCKFISH_EXT" ; exit 1 ;;
esac

echo "`date`: Creating virtual machine..."

# TODO: Remove "beta" once --max-run-duration is in the GA gcloud
gcloud beta compute instances create $GCP_INSTANCE_NAME \
	--project $GCP_PROJECT \
	--zone $GCP_ZONE \
	--machine-type $GCP_MACHINE_TYPE \
	--image-project $GCP_IMAGE_PROJECT \
	--image-family $GCP_IMAGE_FAMILY \
	--provisioning-model $PROVISIONING_MODEL \
	$MAX_RUN_DURATION_FLAGS \
	--metadata=startup-script="sudo apt-get update && \
		sudo apt-get install -y unzip git && \
		curl -sS -L -o $STOCKFISH_DOWNLOAD_TO $STOCKFISH_URL && \
		$STOCKFISH_EXTRACT_COMMAND && \
		chmod a+x ${STOCKFISH_EXTRACT_DIR}/${STOCKFISH_BINARY_PATH} && \
		ln -s ${STOCKFISH_EXTRACT_DIR}/${STOCKFISH_BINARY_PATH} $STOCKFISH_BINARY_LINK && \
		chown ${SSH_USER}:${SSH_USER} -R $STOCKFISH_BINARY_LINK $STOCKFISH_EXTRACT_DIR && \
		git clone https://github.com/amdw/enginecloud.git /home/${SSH_USER}/enginecloud && \
		chown ${SSH_USER}:${SSH_USER} -R /home/${SSH_USER}/enginecloud"

echo "`date`: Virtual machine has been created and should now be consuming billable resources."

until gcloud compute ssh --zone $GCP_ZONE $GCP_INSTANCE_NAME --project $GCP_PROJECT --command "/home/${SSH_USER}/enginecloud/stockfish/benchmarks/sfbench.py $STOCKFISH_BINARY_LINK --quick" --quiet 2>/dev/null
do
	echo "Waiting for machine to be ready..."
	sleep 5
done
echo "`date`: Virtual machine is ready for use!"
