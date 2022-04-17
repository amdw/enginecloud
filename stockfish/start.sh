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

if ! [[ -f stockfish/settings.sh ]]
then
	echo "Could not find settings file: make sure you are running from the root of the repo"
	echo "and have copied stockfish/settings_template.sh to stockfish/settings.sh and filled it in."
	exit 1
fi

source stockfish/settings.sh

if ! [[ -e $EC_HOME ]]; then mkdir $EC_HOME; fi

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
		\`--command="/tmp/stockfish/stockfish"\`,
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

gcloud compute instances create $GCP_INSTANCE_NAME \
    --project $GCP_PROJECT \
    --zone $GCP_ZONE \
    --machine-type $GCP_MACHINE_TYPE \
    --image-project $GCP_IMAGE_PROJECT \
    --image-family $GCP_IMAGE_FAMILY \
    --metadata=startup-script="sudo apt-get install -y wget unzip && \
        wget https://stockfishchess.org/files/${STOCKFISH_VERSION}.zip -O /tmp/stockfish.zip && \
        unzip /tmp/stockfish.zip -d /tmp/stockfish && \
        chmod a+x /tmp/stockfish/${STOCKFISH_VERSION}/${STOCKFISH_VERSION} && \
        ln -s /tmp/stockfish/${STOCKFISH_VERSION}/${STOCKFISH_VERSION} /tmp/stockfish/stockfish && \
        chown ${SSH_USER}:${SSH_USER} -R /tmp/stockfish"

echo "Virtual machine has been created and should now be consuming billable resources."
