# Copyright 2026 Andrew Medworth
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

"""
Multi-VM Stockfish Benchmark Script

Runs sfbench.py across multiple VM types and Stockfish binaries on GCP.
Uses asyncio for concurrent execution with per-family CPU quota limits.
"""

import argparse
import asyncio
import getpass
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger(__name__)

#############################
# CONFIGURATION
#############################

# VM Image settings
GCP_IMAGE_PROJECT = "ubuntu-os-cloud"
GCP_IMAGE_FAMILY = "ubuntu-2404-lts-amd64"
PROVISIONING_MODEL = "SPOT"
MAX_RUN_DURATION = "1h"

# Instance naming
INSTANCE_PREFIX = "sfbench"

# Maximum CPUs to use concurrently per machine type family (GCE quota limits)
# Adjust these based on your project's quota allocations
MAX_CPUS_PER_FAMILY: dict[str, int] = {
    "c4d": 150,
    "c4": 96,
    "c3d": 180,
    "c2d": 56,
}
DEFAULT_MAX_CPUS = 24  # Default if family not specified
GLOBAL_MAX_CPUS = 128  # CPUS_ALL_REGIONS quota limit


@dataclass(frozen=True)
class StockfishBinary:
    """A Stockfish binary to benchmark."""
    name: str
    url: str
    binary_path: str


@dataclass(frozen=True)
class BenchmarkConfig:
    """A specific VM type + Stockfish binary combination to benchmark."""
    machine_type: str
    stockfish: StockfishBinary


# Available Stockfish binaries
# See https://stockfishchess.org/download/linux/ for options
STOCKFISH_AVX512ICL = StockfishBinary(
    name="avx512icl",
    url="https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-avx512icl.tar",
    binary_path="stockfish/stockfish-ubuntu-x86-64-avx512icl",
)

STOCKFISH_VNNI512 = StockfishBinary(
    name="vnni512",
    url="https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-vnni512.tar",
    binary_path="stockfish/stockfish-ubuntu-x86-64-vnni512",
)

STOCKFISH_BMI2 = StockfishBinary(
    name="bmi2",
    url="https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-bmi2.tar",
    binary_path="stockfish/stockfish-ubuntu-x86-64-bmi2",
)

# Benchmark configurations: specific VM type + Stockfish binary combinations
# Not all binaries work on all VM types due to CPU compatibility
BENCHMARK_CONFIGS = [
    # BenchmarkConfig("c4d-standard-2", STOCKFISH_AVX512ICL),
    BenchmarkConfig("c4d-standard-16", STOCKFISH_AVX512ICL),
    BenchmarkConfig("c4d-standard-32", STOCKFISH_AVX512ICL),
    BenchmarkConfig("c4d-standard-64", STOCKFISH_AVX512ICL),
    BenchmarkConfig("c4d-standard-96", STOCKFISH_AVX512ICL),

    # BenchmarkConfig("c4-standard-2", STOCKFISH_AVX512ICL),
    BenchmarkConfig("c4-standard-16", STOCKFISH_AVX512ICL),
    BenchmarkConfig("c4-standard-32", STOCKFISH_AVX512ICL),
    BenchmarkConfig("c4-standard-48", STOCKFISH_AVX512ICL),
    BenchmarkConfig("c4-standard-96", STOCKFISH_AVX512ICL),

    BenchmarkConfig("c3d-standard-16", STOCKFISH_VNNI512),
    BenchmarkConfig("c3d-standard-30", STOCKFISH_VNNI512),
    BenchmarkConfig("c3d-standard-60", STOCKFISH_VNNI512),
    BenchmarkConfig("c3d-standard-90", STOCKFISH_VNNI512),

    BenchmarkConfig("c2d-standard-16", STOCKFISH_BMI2),
    BenchmarkConfig("c2d-standard-32", STOCKFISH_BMI2),
    BenchmarkConfig("c2d-standard-56", STOCKFISH_BMI2),
]


async def run_command_async(args: list[str], check: bool = True,
                            stdout_file: str | None = None,
                            stderr_file: str | None = None) -> subprocess.CompletedProcess:
    """Run a command asynchronously and return the result."""
    LOGGER.debug("Running async: %s", ' '.join(args))

    stdout_handle = None
    stderr_handle = None

    try:
        if stdout_file:
            stdout_handle = open(stdout_file, "a")
        if stderr_file:
            stderr_handle = open(stderr_file, "a")

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=stdout_handle if stdout_handle else asyncio.subprocess.PIPE,
            stderr=stderr_handle if stderr_handle else asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        # returncode is guaranteed to be set after communicate()
        returncode = process.returncode
        assert returncode is not None

        if check and returncode != 0:
            raise subprocess.CalledProcessError(
                returncode, args, stdout, stderr
            )

        return subprocess.CompletedProcess(
            args, returncode,
            stdout.decode() if stdout else "",
            stderr.decode() if stderr else ""
        )
    finally:
        if stdout_handle:
            stdout_handle.close()
        if stderr_handle:
            stderr_handle.close()


def get_machine_family(machine_type: str) -> str:
    """Extract the machine family from a machine type (e.g., 'c4d-standard-16' -> 'c4d')."""
    match = re.match(r'^([a-z0-9]+)-', machine_type)
    if match:
        return match.group(1)
    return machine_type


def get_cpu_count(machine_type: str) -> int:
    """Extract the CPU count from a machine type (e.g., 'c4d-standard-16' -> 16)."""
    match = re.search(r'-(\d+)$', machine_type)
    if match:
        return int(match.group(1))
    return 0


def get_extract_command(url: str, download_path: str, extract_dir: str) -> str:
    """Get the command to extract a Stockfish archive."""
    ext = url.rsplit(".", 1)[-1]
    if ext == "zip":
        return f"unzip {download_path} -d {extract_dir}"
    elif ext == "tar":
        return f"mkdir -p {extract_dir} && tar -xf {download_path} -C {extract_dir}"
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def generate_instance_name(config: BenchmarkConfig) -> str:
    """Generate a unique instance name for a benchmark config."""
    timestamp = int(time.time())
    # Sanitize: lowercase, replace underscores with hyphens, limit length
    name = f"{INSTANCE_PREFIX}-{config.machine_type}-{config.stockfish.name}-{timestamp}"
    name = name.lower().replace("_", "-").replace("/", "-")
    return name[:63]


def get_output_basename(config: BenchmarkConfig) -> str:
    """Generate the base filename for a benchmark config's output files."""
    return f"{config.machine_type}_{config.stockfish.name}".replace("-", "_")


class BenchmarkRun:
    """Encapsulates a single benchmark run on a GCP VM."""

    def __init__(self, config: BenchmarkConfig, project: str, zone: str,
                 ssh_user: str, output_dir: Path):
        self.config = config
        self.project = project
        self.zone = zone
        self.ssh_user = ssh_user
        self.instance_name = generate_instance_name(config)
        basename = get_output_basename(config)
        self.stdout_file = str(output_dir / f"{basename}_stdout.txt")
        self.stderr_file = str(output_dir / f"{basename}_stderr.txt")
        self._stockfish_link = f"/home/{ssh_user}/run_stockfish"

    async def create_vm(self) -> bool:
        """Create a VM with Stockfish installed."""
        extract_dir = f"/home/{self.ssh_user}/stockfish"
        download_path = f"/tmp/stockfish.{self.config.stockfish.url.rsplit('.', 1)[-1]}"

        extract_command = get_extract_command(self.config.stockfish.url, download_path, extract_dir)

        startup_script = " && ".join([
            "sudo apt-get update",
            "sudo apt-get install -y unzip git",
            f"curl -sS -L -o {download_path} {self.config.stockfish.url}",
            extract_command,
            f"chmod a+x {extract_dir}/{self.config.stockfish.binary_path}",
            f"ln -sf {extract_dir}/{self.config.stockfish.binary_path} {self._stockfish_link}",
            f"chown {self.ssh_user}:{self.ssh_user} -R {self._stockfish_link} {extract_dir}",
            f"git clone https://github.com/amdw/enginecloud.git /home/{self.ssh_user}/enginecloud",
            f"chown {self.ssh_user}:{self.ssh_user} -R /home/{self.ssh_user}/enginecloud",
        ])

        LOGGER.info("Creating VM: %s (type: %s, binary: %s)",
                   self.instance_name, self.config.machine_type, self.config.stockfish.name)

        args = [
            "gcloud", "compute", "instances", "create", self.instance_name,
            "--project", self.project,
            "--zone", self.zone,
            "--machine-type", self.config.machine_type,
            "--image-project", GCP_IMAGE_PROJECT,
            "--image-family", GCP_IMAGE_FAMILY,
            "--provisioning-model", PROVISIONING_MODEL,
            f"--metadata=startup-script={startup_script}",
        ]

        if MAX_RUN_DURATION:
            args.extend([
                "--max-run-duration", MAX_RUN_DURATION,
                "--instance-termination-action", "DELETE",
            ])

        try:
            await run_command_async(args, stdout_file=self.stdout_file, stderr_file=self.stderr_file)
            return True
        except subprocess.CalledProcessError as e:
            LOGGER.error("Failed to create VM %s: %s", self.instance_name, e)
            return False

    async def wait_for_vm(self, max_attempts: int = 60, poll_interval: int = 5) -> bool:
        """Wait for a VM to be ready (Stockfish installed and repo cloned)."""
        check_command = f"test -x {self._stockfish_link} && test -d /home/{self.ssh_user}/enginecloud"

        LOGGER.debug("Waiting for VM %s to be ready...", self.instance_name)

        for attempt in range(max_attempts):
            try:
                result = await run_command_async([
                    "gcloud", "compute", "ssh",
                    "--zone", self.zone,
                    self.instance_name,
                    "--project", self.project,
                    f"--command={check_command}",
                    "--quiet",
                ], check=False)
                if result.returncode == 0:
                    LOGGER.debug("VM %s is ready", self.instance_name)
                    return True
            except Exception:
                pass

            if attempt < max_attempts - 1:
                await asyncio.sleep(poll_interval)

        LOGGER.error("VM %s failed to become ready after %d attempts", self.instance_name, max_attempts)
        return False

    async def run_benchmark(self) -> bool:
        """Run the benchmark on a VM, writing output to separate files."""
        benchmark_command = f"/home/{self.ssh_user}/enginecloud/stockfish/benchmarks/sfbench.py {self._stockfish_link}"

        LOGGER.info("Starting benchmark: %s (%s)", self.config.machine_type, self.config.stockfish.name)

        args = [
            "gcloud", "compute", "ssh",
            "--zone", self.zone,
            self.instance_name,
            "--project", self.project,
            f"--command={benchmark_command}",
            "--quiet",
        ]

        try:
            await run_command_async(args, stdout_file=self.stdout_file, stderr_file=self.stderr_file)
            LOGGER.info("Finished benchmark: %s (%s)", self.config.machine_type, self.config.stockfish.name)
            return True
        except subprocess.CalledProcessError as e:
            LOGGER.error("Benchmark failed on %s: %s", self.instance_name, e)
            return False

    async def delete_vm(self) -> None:
        """Delete a VM."""
        LOGGER.info("Deleting VM: %s", self.instance_name)
        try:
            await run_command_async([
                "gcloud", "compute", "instances", "delete", self.instance_name,
                "--project", self.project,
                "--zone", self.zone,
                "--quiet",
            ], stdout_file=self.stdout_file, stderr_file=self.stderr_file)
            LOGGER.info("Deleted VM: %s", self.instance_name)
        except subprocess.CalledProcessError as e:
            LOGGER.warning("Failed to delete VM %s: %s", self.instance_name, e)


def get_last_line(filepath: str) -> str:
    """Get the last line from a file, or empty string if file doesn't exist."""
    try:
        result = subprocess.run(
            ["tail", "-n", "1", filepath],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    except OSError:
        return ""


class ProgressTracker:
    """Tracks active benchmarks for progress reporting."""

    def __init__(self) -> None:
        self._active: dict[str, tuple[BenchmarkConfig, str, float]] = {}  # key -> (config, stderr_file, start_time)
        self._lock = asyncio.Lock()

    async def register(self, key: str, config: BenchmarkConfig, stderr_file: str) -> None:
        """Register a benchmark as active."""
        async with self._lock:
            self._active[key] = (config, stderr_file, time.time())

    async def unregister(self, key: str) -> None:
        """Unregister a benchmark."""
        async with self._lock:
            self._active.pop(key, None)

    async def get_status(self) -> list[tuple[BenchmarkConfig, str, float, str]]:
        """Get status of all active benchmarks: (config, stderr_file, elapsed_secs, last_line)."""
        async with self._lock:
            result = []
            for config, stderr_file, start_time in self._active.values():
                elapsed = time.time() - start_time
                last_line = get_last_line(stderr_file)
                result.append((config, stderr_file, elapsed, last_line))
            return result

    async def has_active(self) -> bool:
        """Check if there are any active benchmarks."""
        async with self._lock:
            return len(self._active) > 0


async def progress_monitor(tracker: ProgressTracker, interval: int = 30) -> None:
    """Periodically log the status of active benchmarks."""
    # Loop indefinitely - this task is cancelled when all benchmarks complete
    while True:
        await asyncio.sleep(interval)
        status = await tracker.get_status()
        if status:
            LOGGER.info("Progress update: %d benchmark(s) running", len(status))
            for config, _, elapsed, last_line in status:
                elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
                truncated_line = last_line[:100] + "..." if len(last_line) > 100 else last_line
                LOGGER.info("  - %s (%s): %s elapsed, latest: %s",
                           config.machine_type, config.stockfish.name, elapsed_str, truncated_line)


class CpuQuotaManager:
    """Manages CPU quota limits per machine type family and globally."""

    def __init__(self, max_cpus_per_family: dict[str, int], default_max: int,
                 global_max: int | None = None):
        self._max_cpus_per_family = max_cpus_per_family
        self._default_max = default_max
        self._global_max = global_max
        self._family_cpus_in_use: dict[str, int] = {}
        self._global_cpus_in_use = 0
        self._lock = asyncio.Lock()

    def _get_max_cpus(self, family: str) -> int:
        return self._max_cpus_per_family.get(family, self._default_max)

    def validate_config(self, machine_type: str) -> None:
        """Raise ValueError if a machine type exceeds its family's or global quota limit."""
        family = get_machine_family(machine_type)
        cpu_count = get_cpu_count(machine_type)
        max_cpus = self._get_max_cpus(family)
        if cpu_count > max_cpus:
            raise ValueError(
                f"Machine type {machine_type} requires {cpu_count} CPUs, "
                f"but family {family} has a maximum quota of {max_cpus} CPUs. "
                f"Increase MAX_CPUS_PER_FAMILY['{family}'] or remove this config."
            )
        if self._global_max is not None and cpu_count > self._global_max:
            raise ValueError(
                f"Machine type {machine_type} requires {cpu_count} CPUs, "
                f"but global quota is only {self._global_max} CPUs."
            )

    async def acquire(self, machine_type: str) -> bool:
        """Acquire CPU quota for a machine type. Blocks until quota is available.

        Atomically acquires both family and global quota to avoid deadlocks.
        """
        family = get_machine_family(machine_type)
        cpu_count = get_cpu_count(machine_type)
        max_family_cpus = self._get_max_cpus(family)

        while True:
            async with self._lock:
                family_usage = self._family_cpus_in_use.get(family, 0)
                family_ok = family_usage + cpu_count <= max_family_cpus
                global_ok = (self._global_max is None or
                             self._global_cpus_in_use + cpu_count <= self._global_max)

                # Only acquire if both quotas are available (atomic acquisition)
                if family_ok and global_ok:
                    self._family_cpus_in_use[family] = family_usage + cpu_count
                    self._global_cpus_in_use += cpu_count
                    LOGGER.debug(
                        "Acquired %d CPUs for %s (family %s: %d/%d, global: %d/%s)",
                        cpu_count, machine_type, family,
                        self._family_cpus_in_use[family], max_family_cpus,
                        self._global_cpus_in_use,
                        self._global_max if self._global_max else "unlimited")
                    return True
            # Wait and retry
            await asyncio.sleep(1)

    async def release(self, machine_type: str) -> None:
        """Release CPU quota for a machine type."""
        family = get_machine_family(machine_type)
        cpu_count = get_cpu_count(machine_type)

        async with self._lock:
            family_usage = self._family_cpus_in_use.get(family, 0)
            self._family_cpus_in_use[family] = max(0, family_usage - cpu_count)
            self._global_cpus_in_use = max(0, self._global_cpus_in_use - cpu_count)
            LOGGER.debug(
                "Released %d CPUs for %s (family %s: %d, global: %d)",
                cpu_count, machine_type, family,
                self._family_cpus_in_use[family], self._global_cpus_in_use)


async def run_single_benchmark(config: BenchmarkConfig, project: str, zone: str,
                               ssh_user: str, output_dir: Path,
                               quota_manager: CpuQuotaManager,
                               progress_tracker: ProgressTracker) -> tuple[BenchmarkConfig, bool]:
    """Run a single benchmark configuration end-to-end."""
    run = BenchmarkRun(config, project, zone, ssh_user, output_dir)
    success = False
    start_time = time.time()

    # Wait for CPU quota
    await quota_manager.acquire(config.machine_type)

    # Register with progress tracker
    await progress_tracker.register(run.instance_name, config, run.stderr_file)

    try:
        if not await run.create_vm():
            return config, False

        if not await run.wait_for_vm():
            return config, False

        success = await run.run_benchmark()

    finally:
        await progress_tracker.unregister(run.instance_name)
        await run.delete_vm()
        await quota_manager.release(config.machine_type)

    elapsed = time.time() - start_time
    elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
    status = "succeeded" if success else "failed"
    LOGGER.info("Benchmark %s: %s (%s) in %s",
               status, config.machine_type, config.stockfish.name, elapsed_str)

    return config, success


async def run_all_benchmarks(configs: list[BenchmarkConfig], project: str, zone: str,
                             ssh_user: str, output_dir: Path,
                             quota_manager: CpuQuotaManager) -> list[tuple[BenchmarkConfig, bool]]:
    """Run all benchmark configurations concurrently with quota management."""
    progress_tracker = ProgressTracker()

    tasks = [
        run_single_benchmark(config, project, zone, ssh_user, output_dir,
                            quota_manager, progress_tracker)
        for config in configs
    ]

    # Start progress monitor as a background task
    monitor_task = asyncio.create_task(progress_monitor(progress_tracker))

    try:
        results = await asyncio.gather(*tasks)
    finally:
        # Cancel the monitor task once all benchmarks complete
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    return list(results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Stockfish benchmarks across multiple VM types concurrently")
    parser.add_argument("--project", required=True, help="GCP project ID")
    parser.add_argument("--zone", required=True, help="GCP zone")
    parser.add_argument("--ssh-user", default=getpass.getuser(), help="SSH username for VMs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print configurations without running benchmarks")
    parser.add_argument("--output-dir", "-o", default="benchmark_output",
                        help="Output directory for benchmark results (default: benchmark_output)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        format='%(asctime)s %(levelname)-6s %(name)-12s: %(message)s',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    # Validate output directory exists
    output_dir = Path(args.output_dir)
    if not output_dir.is_dir():
        parser.error(f"Output directory does not exist: {output_dir.absolute()}")

    # Print header
    print("=" * 60)
    print("Stockfish Multi-VM Benchmark Results")
    print(f"Date: {datetime.now().isoformat()}")
    print(f"Project: {args.project}")
    print(f"Zone: {args.zone}")
    print("=" * 60)
    print()

    if args.dry_run:
        print("Configurations to test:")
        for config in BENCHMARK_CONFIGS:
            cpu_count = get_cpu_count(config.machine_type)
            family = get_machine_family(config.machine_type)
            print(f"  - {config.machine_type} + {config.stockfish.name} ({cpu_count} CPUs, family: {family})")
        print()
        print("CPU quota limits:")
        print(f"  Global (CPUS_ALL_REGIONS): {GLOBAL_MAX_CPUS} CPUs max")
        print("  Per family:")
        for family, max_cpus in MAX_CPUS_PER_FAMILY.items():
            print(f"    - {family}: {max_cpus} CPUs max")
        return

    # Create quota manager once and use for validation and execution
    quota_manager = CpuQuotaManager(MAX_CPUS_PER_FAMILY, DEFAULT_MAX_CPUS, GLOBAL_MAX_CPUS)

    # Validate all configs before starting any tests
    for config in BENCHMARK_CONFIGS:
        quota_manager.validate_config(config.machine_type)

    LOGGER.info("Output directory: %s", output_dir.absolute())

    # Run all benchmarks concurrently
    results = asyncio.run(
        run_all_benchmarks(BENCHMARK_CONFIGS, args.project, args.zone,
                          args.ssh_user, output_dir, quota_manager)
    )

    # Print summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for config, success in results:
        status = "OK" if success else "FAILED"
        print(f"{config.machine_type:20} {config.stockfish.name:15} {status}")

    print()
    print(f"Output files written to: {output_dir.absolute()}")
    print("Benchmark complete!")


if __name__ == "__main__":
    main()
