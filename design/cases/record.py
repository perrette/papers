#!/usr/bin/env python3
"""Record the expected results of the cases by running the reference implementation (papers-cli).

    design/cases/record.py [--papers CMD] [CASE ...]

Each case runs twice, in two fresh sandboxes (a temporary HOME and working folder, so the machine's
own configuration and libraries are never touched); it is recorded only if the two runs agree.
CASE is a glob on the name of the case (group/name), all cases by default.
"""
import argparse
import concurrent.futures
import sys

import conformance as c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--papers', default='papers', help='the reference command (default: papers)')
    ap.add_argument('--with', dest='have', default='', help='comma-separated capabilities available (e.g. network)')
    ap.add_argument('-j', '--jobs', type=int, default=1, metavar='N', help='record N cases at once (default: 1)')
    ap.add_argument('cases', nargs='*', help='glob(s) of case names (default: all)')
    o = ap.parse_args()
    papers = c.resolve_papers(o.papers)
    have = set(filter(None, o.have.split(',')))
    cases = c.find_cases(o.cases)
    if not cases:
        sys.exit('no case found')
    def record(case):
        "(failed, text to print)"
        if set(case.requires) - have:
            return False, f'skip   {case.name} (needs {", ".join(sorted(set(case.requires) - have))})\n'
        first = c.run_case(case, papers)
        second = c.run_case(case, papers)
        diff = c.differences(first, second)
        if diff:
            return True, f'NOT DETERMINISTIC {case.name}: {diff[0][0]}\n{diff[0][1]}\n'
        c.write_expected(case, first)
        return False, f'record {case.name}\n'

    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, o.jobs)) as pool:
        for bad, text in pool.map(record, cases):
            failed += bad
            print(text, end='', file=sys.stderr if bad else sys.stdout, flush=True)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
