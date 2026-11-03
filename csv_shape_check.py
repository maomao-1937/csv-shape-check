#!/usr/bin/env python3
"""Read-only, bounded CSV shape checks for a documented UTF-8 CSV profile."""

import json
import os
import re
import stat
import sys

MAX_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 10_000
MAX_FIELDS = 1_000
MAX_CELL_BYTES = 64 * 1024
MAX_FINDINGS = 10_000

HELP = """Usage: python csv_shape_check.py INPUT [--no-header]
Check a named local UTF-8 CSV file (optional BOM), read-only.
The first record is the header unless --no-header is supplied.
Exit codes: 0 clean, 1 shape findings, 2 invalid input or output failure.
Results are JSON; --help prints this fixed help text.
"""


class InvalidInput(Exception):
    """Neutral input rejection; never contains input content."""


def parse(raw):
    """Parse the bounded profile with an explicit four-state lexical machine."""
    if len(raw) > MAX_BYTES:
        raise InvalidInput
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise InvalidInput from None
    if not text:
        raise InvalidInput
    records, fields, cell = [], [], []
    cell_bytes = 0
    state = 'start'
    active = False

    def append(character):
        nonlocal cell_bytes
        cell_bytes += len(character.encode('utf-8'))
        if cell_bytes > MAX_CELL_BYTES:
            raise InvalidInput
        cell.append(character)

    def end_field():
        nonlocal cell_bytes
        if len(fields) >= MAX_FIELDS:
            raise InvalidInput
        fields.append(''.join(cell))
        cell.clear()
        cell_bytes = 0

    def end_record():
        if len(records) >= MAX_RECORDS:
            raise InvalidInput
        end_field()
        records.append(fields.copy())
        fields.clear()

    index = 0
    while index < len(text):
        character = text[index]
        number = ord(character)
        if (number < 32 and character not in '\r\n') or 127 <= number <= 159:
            raise InvalidInput
        if state == 'quoted':
            if character == '"':
                state = 'closed'
            else:
                append(character)
            index += 1
            continue
        if character in '\r\n':
            if character == '\r':
                if index + 1 >= len(text) or text[index + 1] != '\n':
                    raise InvalidInput
                index += 1
            end_record()
            state, active = 'start', False
        elif character == ',':
            end_field()
            state, active = 'start', True
        elif character == '"':
            if state == 'start':
                state, active = 'quoted', True
            elif state == 'closed':
                append('"')
                state = 'quoted'
            else:
                raise InvalidInput
        else:
            if state == 'closed':
                raise InvalidInput
            append(character)
            state, active = 'unquoted', True
        index += 1
    if state == 'quoted':
        raise InvalidInput
    if active or fields:
        end_record()
    return records


def inspect_bytes(raw, no_header=False):
    """Return counts and fixed findings containing indices/counts only."""
    records = parse(raw)
    width = len(records[0])
    findings = []

    def finding(value):
        if len(findings) >= MAX_FINDINGS:
            raise InvalidInput
        findings.append(value)

    if not no_header:
        seen = {}
        for column, name in enumerate(records[0], 1):
            if name == '':
                finding({'code': 'EMPTY_HEADER', 'record': 1, 'column': column})
            if name in seen:
                finding({'code': 'DUPLICATE_HEADER', 'record': 1,
                         'column': column, 'first_column': seen[name]})
            else:
                seen[name] = column
    for record, fields in enumerate(records, 1):
        if len(fields) != width:
            finding({'code': 'WIDTH_MISMATCH', 'record': record,
                     'expected': width, 'actual': len(fields)})
    header = 0 if no_header else 1
    return {'status': 'findings' if findings else 'clean',
            'counts': {'records': len(records), 'header': header,
                       'data': len(records) - header, 'columns': width},
            'findings': findings}


def read_local(name):
    """Reject nonlocal/device syntax before metadata; read a regular file."""
    if not name or '\x00' in name or re.match(r'^[\\/]{2}', name):
        raise InvalidInput
    if name.startswith('\\??\\'):
        raise InvalidInput
    drive = re.match(r'^[A-Za-z]:[\\/]', name)
    tail = name[2:] if drive else name
    if ':' in tail:
        raise InvalidInput
    for component in re.split(r'[\\/]', tail):
        base = component.rstrip(' .').split('.')[0].rstrip(' ').upper()
        if base in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} or re.fullmatch(r'(COM|LPT)[1-9¹²³]', base):
            raise InvalidInput
    try:
        info = os.stat(name)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise InvalidInput
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0)
        descriptor = os.open(name, flags)
        with os.fdopen(descriptor, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_BYTES:
                raise InvalidInput
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InvalidInput
        return raw
    except (OSError, ValueError):
        raise InvalidInput from None


def emit(value):
    """Flush explicitly; disable shutdown flushing after a closed pipe."""
    try:
        sys.stdout.write(value)
        sys.stdout.flush()
        return True
    except (OSError, ValueError):
        sys.stdout = None
        return False


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ['--help']:
        return 0 if emit(HELP) else 2
    try:
        no_header = '--no-header' in args
        if args.count('--no-header') > 1:
            raise InvalidInput
        names = [arg for arg in args if arg != '--no-header']
        if len(names) != 1 or names[0].startswith('-'):
            raise InvalidInput
        result = inspect_bytes(read_local(names[0]), no_header=no_header)
        code = 1 if result['findings'] else 0
    except Exception:
        result, code = {'status': 'invalid', 'code': 'INVALID_INPUT'}, 2
    output = json.dumps(result, ensure_ascii=True, separators=(',', ':')) + '\n'
    return code if emit(output) else 2


if __name__ == '__main__':
    sys.exit(main())
