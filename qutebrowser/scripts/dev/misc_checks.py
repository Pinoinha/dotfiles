#!/usr/bin/env python3
# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2014-2020 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Various small code checkers."""

import os
import os.path
import re
import sys
import argparse
import subprocess
import tokenize
import traceback
import pathlib
from typing import List, Iterator, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                os.pardir))

from scripts import utils

BINARY_EXTS = {'.png', '.icns', '.ico', '.bmp', '.gz', '.bin', '.pdf',
               '.sqlite', '.woff2', '.whl'}


def _get_files(
        *,
        verbose: bool,
        ignored: List[pathlib.Path] = None
) -> Iterator[pathlib.Path]:
    """Iterate over all files and yield filenames."""
    filenames = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        stdout=subprocess.PIPE,
        universal_newlines=True,
        check=True,
    )
    all_ignored = ignored or []
    all_ignored.append(
        pathlib.Path('tests', 'unit', 'scripts', 'importer_sample', 'chrome'))

    for filename in filenames.stdout.split('\0'):
        path = pathlib.Path(filename)
        is_ignored = any(path == p or p in path.parents for p in all_ignored)
        if not filename or path.suffix in BINARY_EXTS or is_ignored:
            continue

        try:
            with tokenize.open(str(path)):
                pass
        except SyntaxError as e:
            # Could not find encoding
            utils.print_col("{} - maybe {} should be added to BINARY_EXTS?".format(
                str(e).capitalize(), path.suffix), 'yellow')
            continue

        if verbose:
            print(path)

        yield path


def check_git(_args: argparse.Namespace = None) -> bool:
    """Check for uncommitted git files.."""
    if not os.path.isdir(".git"):
        print("No .git dir, ignoring")
        print()
        return False
    untracked = []
    gitst = subprocess.run(['git', 'status', '--porcelain'], check=True,
                           stdout=subprocess.PIPE).stdout
    gitst = gitst.decode('UTF-8').strip()
    for line in gitst.splitlines():
        s, name = line.split(maxsplit=1)
        if s == '??' and name != '.venv/':
            untracked.append(name)
    status = True
    if untracked:
        status = False
        utils.print_col("Untracked files:", 'red')
        print('\n'.join(untracked))
    print()
    return status


def _check_spelling_file(path, fobj, patterns):
    ok = True
    for num, line in enumerate(fobj, start=1):
        for pattern, explanation in patterns:
            if pattern.search(line):
                ok = False
                print(f'{path}:{num}: Found "{pattern.pattern}" - ', end='')
                utils.print_col(explanation, 'blue')
    return ok


def check_spelling(args: argparse.Namespace) -> Optional[bool]:
    """Check commonly misspelled words."""
    # Words which I often misspell
    words = {'behaviour', 'quitted', 'likelyhood', 'sucessfully',
             'occur[^rs .!]', 'seperator', 'explicitely', 'auxillary',
             'accidentaly', 'ambigious', 'loosly', 'initialis', 'convienence',
             'similiar', 'uncommited', 'reproducable', 'an user',
             'convienience', 'wether', 'programatically', 'splitted',
             'exitted', 'mininum', 'resett?ed', 'recieved', 'regularily',
             'underlaying', 'inexistant', 'elipsis', 'commiting', 'existant',
             'resetted', 'similarily', 'informations', 'an url', 'treshold',
             'artefact', 'an unix', 'an utf', 'an unicode'}

    # Words which look better when splitted, but might need some fine tuning.
    words |= {'webelements', 'mouseevent', 'keysequence', 'normalmode',
              'eventloops', 'sizehint', 'statemachine', 'metaobject',
              'logrecord'}

    patterns = [
        (
            re.compile(r'[{}{}]{}'.format(w[0], w[0].upper(), w[1:])),
            "Common misspelling or non-US spelling"
        ) for w in words
    ]
    patterns += [
        (
            re.compile(r'(?i)# noqa(?!: )'),
            "Don't use a blanket 'noqa', use something like 'noqa: X123' instead.",
        ),
        (
            re.compile(r'# type: ignore[^\[]'),
            ("Don't use a blanket 'type: ignore', use something like "
             "'type: ignore[error-code]' instead."),
        ),
        (
            re.compile(r'# type: (?!ignore\[)'),
            "Don't use type comments, use type annotations instead.",
        ),
        (
            re.compile(r': typing\.'),
            "Don't use typing.SomeType, do 'from typing import SomeType' instead.",
        ),
        (
            re.compile(r"""monkeypatch\.setattr\(['"]"""),
            "Don't use monkeypatch.setattr('obj.attr', value), use "
            "setattr(obj, 'attr', value) instead.",
        ),
    ]

    # Files which should be ignored, e.g. because they come from another
    # package
    hint_data = pathlib.Path('tests', 'end2end', 'data', 'hints')
    ignored = [
        pathlib.Path('scripts', 'dev', 'misc_checks.py'),
        pathlib.Path('qutebrowser', '3rdparty', 'pdfjs'),
        hint_data / 'ace' / 'ace.js',
        hint_data / 'bootstrap' / 'bootstrap.css',
    ]

    try:
        ok = True
        for path in _get_files(verbose=args.verbose, ignored=ignored):
            with tokenize.open(str(path)) as f:
                if not _check_spelling_file(path, f, patterns):
                    ok = False
        print()
        return ok
    except Exception:
        traceback.print_exc()
        return None


def check_vcs_conflict(args: argparse.Namespace) -> Optional[bool]:
    """Check VCS conflict markers."""
    try:
        ok = True
        for path in _get_files(verbose=args.verbose):
            if path.suffix in {'.rst', '.asciidoc'}:
                # False positives
                continue
            with tokenize.open(str(path)) as f:
                for line in f:
                    if any(line.startswith(c * 7) for c in '<>=|'):
                        print("Found conflict marker in {}".format(path))
                        ok = False
        print()
        return ok
    except Exception:
        traceback.print_exc()
        return None


def check_userscripts_descriptions(_args: argparse.Namespace = None) -> bool:
    """Make sure all userscripts are described properly."""
    folder = pathlib.Path('misc/userscripts')
    readme = folder / 'README.md'

    described = set()
    for line in readme.open('r'):
        line = line.strip()
        if line == '## Others':
            break

        match = re.fullmatch(r'- \[([^]]*)\].*', line)
        if match:
            described.add(match.group(1))

    present = {path.name for path in folder.iterdir()}
    present -= {'README.md', '.mypy_cache', '__pycache__'}

    missing = present - described
    additional = described - present
    ok = True

    if missing:
        print("Missing userscript descriptions: {}".format(missing))
        ok = False
    if additional:
        print("Additional userscript descriptions: {}".format(additional))
        ok = False

    return ok


def main() -> int:
    checkers = {
        'git': check_git,
        'vcs': check_vcs_conflict,
        'spelling': check_spelling,
        'userscripts': check_userscripts_descriptions,
    }

    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', action='store_true', help='Show checked filenames')
    parser.add_argument('checker',
                        choices=list(checkers) + ['all'],
                        help="Which checker to run.")
    args = parser.parse_args()

    if args.checker == 'all':
        retvals = []
        for name, checker in checkers.items():
            utils.print_title(name)
            retvals.append(checker(args))
        return 0 if all(retvals) else 1

    checker = checkers[args.checker]
    ok = checker(args)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())