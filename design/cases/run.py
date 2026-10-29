#!/usr/bin/env python3
"""Run an implementation of papers on the cases and compare it with the recorded results.

    design/cases/run.py --papers CMD [--contract-only] [--section PATTERN] [--test PATTERN] [CASE ...]

CMD is the implementation: `papers`, `path/to/other-papers`... (a program name, or a path, with
optional arguments). CASE is a glob on the name of the case (group/name), all cases by default.
Each case runs in a fresh sandbox (a temporary HOME and working folder). Exit status 0 when all pass.

By default every output is compared byte for byte. With --contract-only only what the specification
makes Contract is: the exit codes, the files after, and the outputs of the steps that are Contract
(see README.md, "Contract and Free"); a difference in a Free output is reported as a note, not a failure.
--section PATTERN keeps the cases that exercise a section of the specification (a glob on its
reference, or a section above it: `formats.md#7` finds the cases of `formats.md#7.2`); it can be repeated.
--test PATTERN keeps the cases that list a test of the specification (design/tests.md, `tests/test_undo.py::...`:
a glob, or a part of the test id).
"""
import argparse
import concurrent.futures
import sys

import conformance as c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--papers', help='the implementation to test')
    ap.add_argument('--with', dest='have', default='', help='comma-separated capabilities available (e.g. network)')
    ap.add_argument('--contract-only', action='store_true',
                    help='compare the Contract parts only; differences in Free outputs are notes')
    ap.add_argument('--section', action='append', default=[], metavar='PATTERN',
                    help='only the cases of this section of the specification (e.g. formats.md#7)')
    ap.add_argument('--test', action='append', default=[], metavar='PATTERN',
                    help='only the cases that list this test of design/tests.md (a glob or a part of its id)')
    ap.add_argument('-a', '--all', action='store_true', help='show every difference, not only the first')
    ap.add_argument('-q', '--quiet', action='store_true', help='only the failures and the summary')
    ap.add_argument('-j', '--jobs', type=int, default=1, metavar='N', help='run N cases at once (default: 1)')
    ap.add_argument('--keep', action='store_true', help='keep the sandboxes (their paths are printed)')
    ap.add_argument('--list', action='store_true', help='list the cases (with their sections) and stop')
    ap.add_argument('--sections', action='store_true', help='list the sections and their cases and stop')
    ap.add_argument('--tests', action='store_true', help='list the tests of design/tests.md and their cases and stop')
    ap.add_argument('cases', nargs='*', help='glob(s) of case names (default: all)')
    o = ap.parse_args()
    cases = c.find_cases(o.cases, o.section, o.test)
    if o.list:
        for case in cases:
            print(case.name + (f'  (needs {", ".join(case.requires)})' if case.requires else '')
                  + '  [' + ', '.join(case.sections) + ']' + (f'  <{len(case.tests)} tests>' if case.tests else ''))
        return
    if o.sections:
        by_section = {}
        for case in cases:
            for ref in case.sections:
                by_section.setdefault(ref, []).append(case.name)
        for ref in sorted(by_section):
            print(f'{ref}: {", ".join(by_section[ref])}')
        return
    if o.tests:
        by_test = {}
        for case in cases:
            for t in case.tests:
                by_test.setdefault(t, []).append(case.name)
        for t in sorted(by_test):
            print(f'{t}: {", ".join(by_test[t])}')
        return
    if not cases:
        sys.exit('no case found')
    if not o.papers:
        ap.error('--papers is required')
    papers = c.resolve_papers(o.papers)
    have = set(filter(None, o.have.split(',')))
    passed = failed = skipped = noted = 0

    def check(case):
        "(status, text to print) of one case: 'skip', 'pass', 'note' (passed with Free differences) or 'fail'"
        missing = set(case.requires) - have
        if missing:
            return 'skip', f'SKIP {case.name} (needs {", ".join(sorted(missing))})\n'
        expected = c.read_expected(case)
        if expected is None:
            return 'fail', f'FAIL {case.name}: not recorded (design/cases/record.py)\n'
        actual = c.run_case(case, papers, keep=o.keep)
        diff = c.differences(expected, actual, case, first_only=not o.all, contract_only=o.contract_only)
        failures = [d for d in diff if not (d[2] and o.contract_only)]
        notes = [d for d in diff if d[2] and o.contract_only]
        out = ''
        if not failures:
            out = f'PASS {case.name}' + (f' (Free differences: {", ".join(n[0] for n in notes)})' if notes else '') + '\n'
            if notes and o.all:
                for label, text, _ in notes:
                    out += f'  -- note, Free: {label}\n'
                    out += ''.join('     ' + line for line in text.splitlines(True))
            return ('note' if notes else 'pass'), out
        out = f'FAIL {case.name}\n'
        for label, text, free in diff:
            out += f'  -- {label}' + (' (Free: a note)' if free and o.contract_only else '') + '\n'
            out += ''.join('     ' + line for line in text.splitlines(True))
        return 'fail', out

    # the cases are independent (each has its own sandbox): -j runs several at once, the report keeps their order
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, o.jobs)) as pool:
        for status, text in pool.map(check, cases):
            if status == 'skip':
                skipped += 1
            elif status == 'fail':
                failed += 1
            else:
                passed += 1
                noted += status == 'note'
            if status == 'fail' or not o.quiet:
                print(text, end='', flush=True)
    print(f'{passed} passed, {failed} failed' + (f', {skipped} skipped' if skipped else '')
          + f' of {len(cases)} cases' + (f' ({noted} with differences in Free outputs)' if o.contract_only else ''))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
