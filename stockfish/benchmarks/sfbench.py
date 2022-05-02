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
import itertools
import re
import statistics
import subprocess
import sys
from typing import Callable, Iterable, Mapping, Sequence


@dataclass(frozen=True, order=True)
class BenchParams:
    """Parameters of an individual stockfish bench run."""
    threads: int
    tt_size_mb: int
    depth: int


@dataclass(frozen=True)
class SeriesParams:
    """Parameters of a sequence of runs."""
    # Number of times to repeat each individual BenchParams combination
    repetitions: int
    # Number of consecutive times we should tolerate a failure to improve on the previous best performance
    max_failures_to_improve: int
    # Function to allow us to force continuing to the next BenchParams even if we would otherwise stop
    force_continue: Callable[[BenchParams], bool]


def run_benchmark(stockfish_binary: str, params: BenchParams) -> Mapping[str, int]:
    print(f'Running {stockfish_binary} bench with {params}...', file=sys.stderr)
    output = subprocess.check_output([
        stockfish_binary, 'bench',
        str(params.tt_size_mb), # ttSize
        str(params.threads),    # threads
        str(params.depth),      # limit
    ], stderr=subprocess.STDOUT, encoding='utf8')
    lines = output.splitlines()
    result = {}
    for line in reversed(lines):
        m = re.match(r'([^:]+\S)\s*:\s+(\d+)', line)
        if not m:
            break
        result[m.group(1)] = int(m.group(2))
    print(f'Run complete: {result}')
    return result


def run_series(
    stockfish_binary: str,
    series_params: SeriesParams,
    params_seq: Iterable[BenchParams],
) -> Mapping[BenchParams, Sequence[int]]:
    results = collections.defaultdict(list)
    best_average = 0
    failures_to_improve = 0
    for params in params_seq:
        while len(results[params]) < series_params.repetitions:
            result = run_benchmark(stockfish_binary, params)
            results[params].append(result['Nodes/second'])
        average = statistics.mean(results[params])
        if average > best_average:
            failures_to_improve = 0
            print(f'Average {average:,.1f} is an improvement on best {best_average:,.1f}', file=sys.stderr)
            best_average = average
        else:
            failures_to_improve += 1
            print(f'Average {average:,.1f} is not an improvement on best {best_average:,.1f}: failures={failures_to_improve}', file=sys.stderr)
            if not series_params.force_continue(params) and failures_to_improve >= series_params.max_failures_to_improve:
                break

    return results


def run_varying_threads(
    stockfish_binary: str,
    depth: int,
    tt_size_mb: int,
    repetitions: int,
    max_failures_to_improve: int,
    min_final_threads: int,
) -> Mapping[BenchParams, Sequence[int]]:
    def force_continue(params: BenchParams):
        return params.threads < min_final_threads

    series_params = SeriesParams(
        repetitions=repetitions,
        max_failures_to_improve=max_failures_to_improve,
        force_continue=force_continue,
    )
    return run_series(
        stockfish_binary,
        series_params,
        (BenchParams(threads=t, tt_size_mb=tt_size_mb, depth=depth) for t in itertools.count(start=1, step=1)),
    )


def print_results(machine_type: str, results: Mapping[BenchParams, Sequence[int]]):
    w = csv.writer(sys.stdout)
    for (params, nps_results) in sorted(results.items()):
        row = [machine_type, params.threads, params.tt_size_mb, params.depth]
        row.extend(nps_results)
        row.append(statistics.mean(nps_results))
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
    parser.add_argument('--tt_size_mb', type=int, default=16)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--max_failures_to_improve', type=int, default=3)
    args = parser.parse_args()
    machine_type = get_machine_type()
    machtype_cpus = int(machine_type.split('-')[-1])
    results = run_varying_threads(
        args.stockfish_binary, args.depth, args.tt_size_mb,
        args.repetitions, args.max_failures_to_improve, machtype_cpus)
    print_results(machine_type, results)


if __name__ == '__main__':
    main()
