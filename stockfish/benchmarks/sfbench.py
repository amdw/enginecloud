#!/usr/bin/env python3
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

"""Stockfish benchmark script."""

import argparse
import collections
import csv
from dataclasses import dataclass
import dataclasses
from datetime import datetime, timezone
import itertools
import logging
import operator
import os.path
import re
import statistics
import subprocess
import sys
from typing import Any, Callable, Iterable, List, Mapping, MutableMapping, Sequence, Union

LOGGER = logging.getLogger('sfbench')


@dataclass(frozen=True, order=True)
class BenchParams:
    """Parameters of an individual stockfish bench run."""
    threads: Union[int, float]
    tt_size_mb: Union[int, float]
    depth: Union[int, float]


@dataclass(frozen=True)
class BenchResult:
    """Result of a single benchmark run."""
    nps: int
    nodes_searched: int
    total_time_ms: int
    time: datetime

RESULT_KEYS = {
    'Nodes/second': 'nps',
    'Nodes searched': 'nodes_searched',
    'Total time (ms)': 'total_time_ms',
}


@dataclass(frozen=True)
class SeriesParams:
    """Parameters of a sequence of runs."""
    # Number of times to repeat each individual BenchParams combination
    repetitions: int
    # Number of consecutive times we should tolerate a failure to improve on the previous best performance
    max_failures_to_improve: int


def run_benchmark(stockfish_binary: str, params: BenchParams) -> BenchResult:
    LOGGER.info('Running %s bench with %s...', stockfish_binary, params)
    output = subprocess.check_output([
        stockfish_binary, 'bench',
        str(params.tt_size_mb), # ttSize
        str(params.threads),    # threads
        str(params.depth),      # limit
    ], stderr=subprocess.STDOUT, encoding='utf8')
    vals: MutableMapping[str, Any] = {'time': datetime.utcnow().replace(tzinfo=timezone.utc)}
    for line in reversed(output.splitlines()):
        m = re.match(r'([^:]+\S)\s*:\s+(\d+)', line)
        if not m:
            break
        (key, val) = (m.group(1), int(m.group(2)))
        vals[RESULT_KEYS[key]] = val
    result = BenchResult(**vals)
    LOGGER.info('Run complete: %s', result)
    return result


def get_average_result(results: Sequence[BenchResult]) -> BenchResult:
    average_values = {f.name: statistics.mean(getattr(r, f.name) for r in results)
                      for f in dataclasses.fields(results[0])
                      if f.name != 'time'}
    return BenchResult(time=max(r.time for r in results), **average_values)


def has_improvement(result: BenchResult, best_so_far: BenchResult) -> bool:
    return (result.nps > best_so_far.nps or
            result.nodes_searched > best_so_far.nodes_searched or
            result.total_time_ms < best_so_far.total_time_ms)


def get_best_values(result1: BenchResult, result2: BenchResult) -> BenchResult:
    return BenchResult(
        nps=max(result1.nps, result2.nps),
        nodes_searched=max(result1.nodes_searched, result2.nodes_searched),
        total_time_ms=min(result1.total_time_ms, result2.total_time_ms),
        time=result1.time if result1.nps > result2.nps else result2.time)


def run_series(
    stockfish_binary: str,
    series_params: SeriesParams,
    force_continue: Callable[[BenchParams], bool],
    params_seq: Iterable[BenchParams],
) -> Mapping[BenchParams, Sequence[BenchResult]]:
    results: Mapping[BenchParams, List[BenchResult]] = collections.defaultdict(list)
    best_values = BenchResult(nps=0, nodes_searched=0, total_time_ms=1000000000000, time=datetime.utcnow().replace(tzinfo=timezone.utc))
    failures_to_improve = 0
    for params in params_seq:
        failure = False
        while len(results[params]) < series_params.repetitions:
            try:
                result = run_benchmark(stockfish_binary, params)
                results[params].append(result)
            except subprocess.CalledProcessError as e:
                failure = True
                LOGGER.error('Run failed: %s', e)
                break
        if failure:
            break
        average = get_average_result(results[params])
        if has_improvement(average, best_values):
            failures_to_improve = 0
            LOGGER.info('Average %s has an improvement on best %s', average, best_values)
            best_values = get_best_values(average, best_values)
        else:
            failures_to_improve += 1
            LOGGER.info('Average %s has no improvement on best %s: failures=%s', average, best_values, failures_to_improve)
            if not force_continue(params) and failures_to_improve >= series_params.max_failures_to_improve:
                break

    return results


def run_varying_threads(
    stockfish_binary: str,
    depth: int,
    tt_size_mb: int,
    series_params: SeriesParams,
    min_final_threads: int,
) -> Mapping[BenchParams, Sequence[BenchResult]]:
    def force_continue(params: BenchParams):
        return params.threads < min_final_threads

    thread_counts = itertools.count(start=1, step=1)
    return run_series(
        stockfish_binary,
        series_params,
        force_continue,
        (BenchParams(threads=t, tt_size_mb=tt_size_mb, depth=depth) for t in thread_counts),
    )


def run_varying_ttsize(
    stockfish_binary: str,
    depth: int,
    threads: int,
    series_params: SeriesParams,
) -> Mapping[BenchParams, Sequence[BenchResult]]:
    # Start with the default and increase by 2x each time
    hash_sizes = itertools.accumulate(itertools.repeat(2), func=operator.mul, initial=16)
    return run_series(
        stockfish_binary,
        series_params,
        lambda p: False,
        (BenchParams(threads=threads, tt_size_mb=size, depth=depth) for size in hash_sizes),
    )


@dataclass(frozen=True)
class CPUInfo:
    """CPU information retrieved from /proc/cpuinfo."""
    processors: int
    cores: int
    physicals: int
    models: str


@dataclass(frozen=True)
class MachineInfo:
    """Machine information retrieved from GCE Metadata Server."""
    machine_type: str
    vcpu_count: int
    cpu_platform: str
    cpu_info: CPUInfo
    instance_id: str
    image: str
    zone: str


@dataclass(frozen=True)
class StockfishInfo:
    """Information about the Stockfish binary run in the benchmark."""
    binary: str
    version: str
    compiler: str
    compilation_settings: str


def print_results(machine_info: MachineInfo, stockfish_info: StockfishInfo, results: Mapping[BenchParams, Sequence[BenchResult]]):
    w = csv.writer(sys.stdout)
    header = [
        'StockfishBinary', 'StockfishVersion', 'StockfishCompiler', 'StockfishCompilationSettings',
        'MachineType', 'VCpuCount', 'CpuPlatform', 'CpuProcessors', 'CpuCores', 'CpuPhysicals', 'CpuModels', 'InstanceID', 'Image', 'Zone',
        'Threads', 'TTSizeMb', 'Depth', 'RunTime', 'NPS', 'TotalTimeMS', 'NodesSearched']
    w.writerow(header)
    for params in sorted(results.keys()):
        params_values = [
            stockfish_info.binary, stockfish_info.version, stockfish_info.compiler, stockfish_info.compilation_settings,
            machine_info.machine_type, machine_info.vcpu_count, machine_info.cpu_platform,
            machine_info.cpu_info.processors, machine_info.cpu_info.cores, machine_info.cpu_info.physicals, machine_info.cpu_info.models,
            machine_info.instance_id, machine_info.image, machine_info.zone,
            params.threads, params.tt_size_mb, params.depth]
        for result in results[params]:
            row = list(params_values)
            row.extend([result.time.isoformat(), result.nps, result.total_time_ms, result.nodes_searched])
            w.writerow(row)


def get_metadata(path: str) -> str:
    """Get metadata from GCE Metadata Server."""
    return subprocess.check_output(
        ['curl', '-s', f'http://metadata.google.internal{path}',
         '-H', 'Metadata-Flavor: Google'],
         encoding='utf8')


def get_cpu_info() -> CPUInfo:
    """Load processor information from /proc/cpuinfo."""
    processors = set()
    cores = set()
    physicals = set()
    models: MutableMapping[str, int] = collections.defaultdict(int)
    last_model = None
    with open('/proc/cpuinfo', encoding='utf8') as f:
        for line in f:
            if m := re.match(r'processor\s*:\s*(\d+)', line):
                processors.add(int(m.group(1)))
            elif m := re.match(r'model name\s*:\s*(.*)', line):
                last_model = m.group(1)
            elif m := re.match(r'cpu MHz\s*:\s*([\d.]+)', line):
                models[f'{last_model} ({m.group(1)} MHz)'] += 1
            elif m := re.match(r'physical id\s*:\s*(\d+)', line):
                physicals.add(int(m.group(1)))
            elif m := re.match(r'core id\s*:\s*(\d+)', line):
                cores.add(int(m.group(1)))

    models_summary = ', '.join(f'{model} * {count}' for (model, count) in sorted(models.items(), key=lambda t: (-t[1], t[0])))
    return CPUInfo(processors=len(processors), cores=len(cores), physicals=len(physicals), models=models_summary)


def get_machine_info() -> MachineInfo:
    machine_type = get_metadata('/computeMetadata/v1/instance/machine-type')
    cpu_info = get_cpu_info()
    m = re.search(r'-(\d+)$', machine_type)
    vcpu_count = int(m.group(1)) if m else cpu_info.processors

    return MachineInfo(
        machine_type=machine_type.rsplit('/', maxsplit=1)[-1].strip(),
        vcpu_count=vcpu_count,
        cpu_platform=get_metadata('/computeMetadata/v1/instance/cpu-platform'),
        cpu_info=cpu_info,
        instance_id=get_metadata('/computeMetadata/v1/instance/id'),
        image=get_metadata('/computeMetadata/v1/instance/image').rsplit('/', maxsplit=1)[-1].strip(),
        zone=get_metadata('/computeMetadata/v1/instance/zone').rsplit('/', maxsplit=1)[-1].strip(),
    )


def get_stockfish_info(binary: str) -> StockfishInfo:
    real_path = os.path.realpath(binary)
    compiler_output = subprocess.check_output([binary, 'compiler'], encoding='utf8')
    parts = {}
    for line in compiler_output.splitlines():
        if m := re.match(r'Stockfish ([\d.-]+)', line):
            parts['version'] = m.group(1)
        elif m := re.match(r'Compiled by[\s:]+(.*)', line):
            parts['compiler'] = m.group(1)
        elif m := re.match(r'Compilation settings[^:]*:\s+(.*)', line):
            parts['compilation_settings'] = m.group(1)
    return StockfishInfo(binary=os.path.basename(real_path), **parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stockfish_binary')
    parser.add_argument('--depth', type=int, default=14)
    parser.add_argument('--threads', type=int, default=0)
    parser.add_argument('--tt_size_mb', type=int, default=16)
    parser.add_argument('--test_varying', type=str, choices=['threads', 'ttsize'], default='threads')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--max_failures_to_improve', type=int, default=3)
    parser.add_argument('--quick', action=argparse.BooleanOptionalAction)
    args = parser.parse_args()

    logging.basicConfig(stream=sys.stderr, format='%(asctime)s %(levelname)-6s %(name)-8s: %(message)s',
                        level=logging.INFO)

    machine_info = get_machine_info()
    stockfish_info = get_stockfish_info(args.stockfish_binary)
    if args.quick:
        print(f'Stockfish: {stockfish_info}')
        print(f'CPU Platform: {machine_info.cpu_platform}; CPU info: {machine_info.cpu_info}')
        result = run_benchmark(args.stockfish_binary, BenchParams(threads=machine_info.vcpu_count, tt_size_mb=args.tt_size_mb, depth=args.depth))
        print(f'Stockfish benchmark with {machine_info.vcpu_count} threads: {result.nps:,.1f} nps ({result.nps / machine_info.vcpu_count:,.1f} nps per vCPU)')
        return

    series_params = SeriesParams(repetitions=args.repetitions, max_failures_to_improve=args.max_failures_to_improve)
    if args.test_varying == 'threads':
        results = run_varying_threads(
            args.stockfish_binary, args.depth, args.tt_size_mb,
            series_params, machine_info.vcpu_count)
    elif args.test_varying == 'ttsize':
        threads = args.threads if args.threads >= 1 else machine_info.vcpu_count
        results = run_varying_ttsize(
            args.stockfish_binary, args.depth, threads, series_params)
    else:
        raise ValueError(f'Unsupported test_varying {args.test_varying}')

    print_results(machine_info, stockfish_info, results)


if __name__ == '__main__':
    main()
