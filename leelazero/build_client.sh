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

cat > ${EC_HOME}/run_lc0.go <<EOF
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
		\`--command="/home/${SSH_USER}/lc0/build/release/lc0"\`,
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
( cd $EC_HOME && go build run_lc0.go ) && echo "Built $EC_HOME/run_lc0"
