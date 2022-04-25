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
import itertools
import re
import statistics
import subprocess
import sys
from typing import Mapping, Sequence

DEFAULT_TTSIZE = 16


def run_benchmark(stockfish_binary: str, threads: int, depth: int) -> Mapping[str, int]:
    print(f'Running {stockfish_binary} bench with {threads} threads, depth {depth}...', file=sys.stderr)
    output = subprocess.check_output([
        stockfish_binary, 'bench',
        str(DEFAULT_TTSIZE), # ttSize
        str(threads),        # threads
        str(depth),          # limit
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


def run_benchmarks(
    stockfish_binary: str,
    depth: int,
    repetitions: int,
    max_failures_to_improve: int,
    min_final_threads: int,
) -> Mapping[int, Sequence[int]]:
    results = collections.defaultdict(list)
    best_average = 0
    failures_to_improve = 0
    for threads in itertools.count(start=1, step=1):
        while len(results[threads]) < repetitions:
            result = run_benchmark(stockfish_binary, threads, depth)
            results[threads].append(result['Nodes/second'])
        average = statistics.mean(results[threads])
        if average > best_average:
            failures_to_improve = 0
            print(f'Average {average:,.1f} is an improvement on best {best_average:,.1f}', file=sys.stderr)
            best_average = average
        else:
            failures_to_improve += 1
            print(f'Average {average:,.1f} is not an improvement on best {best_average:,.1f}: failures={failures_to_improve}', file=sys.stderr)
            if threads > min_final_threads and failures_to_improve >= max_failures_to_improve:
                break

    return results


def print_results(machine_type: str, results: Mapping[int, Sequence[int]]):
    for (threads, nps_results) in sorted(results.items()):
        print(f'{machine_type},{threads},', end='')
        for nps in nps_results:
            print(f'{nps},', end='')
        print(f'{statistics.mean(nps_results)}')


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
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--max_failures_to_improve', type=int, default=3)
    args = parser.parse_args()
    machine_type = get_machine_type()
    machtype_cpus = int(machine_type.split('-')[-1])
    results = run_benchmarks(
        args.stockfish_binary, args.depth, args.repetitions, args.max_failures_to_improve, machtype_cpus)
    print_results(machine_type, results)


if __name__ == '__main__':
    main()
