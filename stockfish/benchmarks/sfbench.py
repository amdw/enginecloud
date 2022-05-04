#!/usr/bin/env python3
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

import argparse
import collections
import csv
from dataclasses import dataclass
import dataclasses
import itertools
import operator
import re
import statistics
import subprocess
import sys
from typing import Callable, Iterable, List, Mapping, Sequence, Union


@dataclass(frozen=True, order=True)
class BenchParams:
    """Parameters of an individual stockfish bench run."""
    threads: Union[int, float]
    tt_size_mb: Union[int, float]
    depth: Union[int, float]


@dataclass(frozen=True)
class BenchResult:
    nps: int
    nodes_searched: int
    total_time_ms: int

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
    print(f'Running {stockfish_binary} bench with {params}...', file=sys.stderr)
    output = subprocess.check_output([
        stockfish_binary, 'bench',
        str(params.tt_size_mb), # ttSize
        str(params.threads),    # threads
        str(params.depth),      # limit
    ], stderr=subprocess.STDOUT, encoding='utf8')
    vals = {}
    for line in reversed(output.splitlines()):
        m = re.match(r'([^:]+\S)\s*:\s+(\d+)', line)
        if not m:
            break
        (key, val) = (m.group(1), int(m.group(2)))
        vals[RESULT_KEYS[key]] = val
    result = BenchResult(**vals)
    print(f'Run complete: {result}')
    return result


def get_average_result(results: Sequence[BenchResult]) -> BenchResult:
    average_values = {f.name: statistics.mean(getattr(r, f.name) for r in results)
                      for f in dataclasses.fields(results[0])}
    return BenchResult(**average_values)


def has_improvement(result: BenchResult, best_so_far: BenchResult) -> bool:
    return (result.nps > best_so_far.nps or
            result.nodes_searched > best_so_far.nodes_searched or
            result.total_time_ms < best_so_far.total_time_ms)


def get_best_values(result1: BenchResult, result2: BenchResult) -> BenchResult:
    return BenchResult(
        nps=max(result1.nps, result2.nps),
        nodes_searched=max(result1.nodes_searched, result2.nodes_searched),
        total_time_ms=min(result1.total_time_ms, result2.total_time_ms))


def run_series(
    stockfish_binary: str,
    series_params: SeriesParams,
    force_continue: Callable[[BenchParams], bool],
    params_seq: Iterable[BenchParams],
) -> Mapping[BenchParams, Sequence[BenchResult]]:
    results: Mapping[BenchParams, List[BenchResult]] = collections.defaultdict(list)
    best_values = BenchResult(nps=0, nodes_searched=0, total_time_ms=1000000000000)
    failures_to_improve = 0
    for params in params_seq:
        failure = False
        while len(results[params]) < series_params.repetitions:
            try:
                result = run_benchmark(stockfish_binary, params)
                results[params].append(result)
            except subprocess.CalledProcessError as e:
                failure = True
                print(f'Run failed: {e}', file=sys.stderr)
                break
        if failure:
            break
        average = get_average_result(results[params])
        if has_improvement(average, best_values):
            failures_to_improve = 0
            print(f'Average {average} has an improvement on best {best_values}', file=sys.stderr)
            best_values = get_best_values(average, best_values)
        else:
            failures_to_improve += 1
            print(f'Average {average} has no improvement on best {best_values}: failures={failures_to_improve}', file=sys.stderr)
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


def print_results(machine_type: str, results: Mapping[BenchParams, Sequence[BenchResult]]):
    w = csv.writer(sys.stdout)
    header = ['MachineType', 'Threads', 'TTSizeMb', 'Depth', 'MeanNPS', 'MeanTotalTimeMS', 'MeanNodesSearched']
    for i in range(1, len(next(iter(results.values()))) + 1):
        header.extend([f'Run{i}NPS', f'Run{i}TotalTimeMS', f'Run{i}NodesSearched'])
    w.writerow(header)
    for params in sorted(results.keys()):
        row = [machine_type, params.threads, params.tt_size_mb, params.depth]
        params_results = results[params]
        if params_results:
            average_results = get_average_result(params_results)
            row.extend([average_results.nps, average_results.total_time_ms, average_results.nodes_searched])
            for result in params_results:
                row.extend([result.nps, result.total_time_ms, result.nodes_searched])
        w.writerow(row)


def get_machine_type() -> str:
    metadata = subprocess.check_output(
        ['curl', '-s', 'http://metadata.google.internal/computeMetadata/v1/instance/machine-type',
         '-H', 'Metadata-Flavor: Google'],
         encoding='utf8')
    return metadata.split('/')[-1].strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stockfish_binary', default='/tmp/stockfish/stockfish', nargs='?')
    parser.add_argument('--depth', type=int, default=14)
    parser.add_argument('--threads', type=int, default=0)
    parser.add_argument('--tt_size_mb', type=int, default=16)
    parser.add_argument('--test_varying', type=str, choices=['threads', 'ttsize'], default='threads')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--max_failures_to_improve', type=int, default=3)
    parser.add_argument('--machine_type', type=str, default='',
        help='Override machine type; leave blank to query from metadata server')
    args = parser.parse_args()

    machine_type = args.machine_type if args.machine_type else get_machine_type()
    machtype_cpus = int(machine_type.split('-')[-1])
    series_params = SeriesParams(repetitions=args.repetitions, max_failures_to_improve=args.max_failures_to_improve)
    if args.test_varying == 'threads':
        results = run_varying_threads(
            args.stockfish_binary, args.depth, args.tt_size_mb,
            series_params, machtype_cpus)
    elif args.test_varying == 'ttsize':
        threads = args.threads if args.threads >= 1 else machtype_cpus
        results = run_varying_ttsize(
            args.stockfish_binary, args.depth, threads, series_params)
    else:
        raise ValueError(f'Unsupported test_varying {args.test_varying}')

    print_results(machine_type, results)


if __name__ == '__main__':
    main()
