# csv-shape-check

[![tests](https://github.com/maomao-1937/csv-shape-check/actions/workflows/tests.yml/badge.svg)](https://github.com/maomao-1937/csv-shape-check/actions/workflows/tests.yml)

A small, read-only Python command that checks CSV record widths and header shape.
It emits JSON counts and numeric locations without printing file paths, header
names, or cell values. Python 3.11 standard library only; no dependencies,
installation step, configuration file, telemetry, or network access.

## Source quickstart

Download or clone this repository and open a terminal in its root directory.
Use Python 3.11 (on some systems the command is `python3`).

```sh
python --version
python csv_shape_check.py examples/clean.csv
python csv_shape_check.py examples/findings.csv
python csv_shape_check.py examples/no-header.csv --no-header
python csv_shape_check.py --help
python -m unittest discover -s tests -v
```

中文快速开始：下载或克隆源码，在项目根目录打开终端。需要 Python 3.11，
无需 `pip install`、第三方依赖或配置文件。运行上面的命令即可。
默认首条记录为表头；没有表头时加 `--no-header`。退出码 `0` 表示未发现问题，
`1` 表示表头或列数问题，`2` 表示输入、语法、上限或输出错误。
JSON 只包含统计、固定问题代码和数字位置，不打印路径、表头名或单元格内容。

## Output and exit codes

For `examples/clean.csv` (exit **0**):

```json
{"status":"clean","counts":{"records":3,"header":1,"data":2,"columns":2},"findings":[]}
```

For `examples/findings.csv` (exit **1**):

```json
{"status":"findings","counts":{"records":2,"header":1,"data":1,"columns":3},"findings":[{"code":"DUPLICATE_HEADER","record":1,"column":2,"first_column":1},{"code":"EMPTY_HEADER","record":1,"column":3},{"code":"WIDTH_MISMATCH","record":2,"expected":3,"actual":2}]}
```

Invalid input, unsupported syntax, inaccessible/nonregular files, exceeded limits,
or invalid arguments return **2** with only:

```json
{"status":"invalid","code":"INVALID_INPUT"}
```

`--help` alone prints fixed text and returns 0. If stdout is closed or writing
fails, the command returns 2; delivery of JSON is then impossible. No traceback or
raw operating system errors are emitted. Output has stable key and finding order.

Counts refer to **logical records**, not physical lines. `header` is 1 by default
and 0 with `--no-header`; `data` excludes that header; `columns` is the first
record's width. All finding locations are 1-based. Findings appear first in header
column order, then in record order for widths:

| Code | Numeric properties | Meaning |
| --- | --- | --- |
| `EMPTY_HEADER` | `record`, `column` | Decoded header is exactly empty |
| `DUPLICATE_HEADER` | `record`, `column`, `first_column` | Exact repeated decoded header |
| `WIDTH_MISMATCH` | `record`, `expected`, `actual` | Width differs from first record |

Empty repeated headers produce both empty and duplicate findings. Comparison is
case-sensitive with no whitespace trimming or Unicode normalization. Header-only
files can be clean. In `--no-header` mode the first record is data and defines
width; header checks do not run. There is no semantic typing, schema inference,
formula checking, repair, or validation of values inside cells.

## Accepted CSV profile

This is a deliberate profile, not a claim of universal CSV or full RFC compliance:

- UTF-8 with an optional leading UTF-8 BOM; comma delimiter; double quote quoting.
- LF or CRLF record endings, including mixed endings; a final ending is optional.
- Quotes may start only at the start of a field. Inside quoted fields, `""`
  decodes to one quote. Quoted commas and LF, CRLF, or bare CR are preserved.
- After a closing quote only a comma, record ending, escaped quote, or EOF is
  valid. Whitespace after a closing quote is invalid.
- Bare CR outside quotes, a quote inside an unquoted field, unfinished quotes,
  invalid UTF-8, NUL, TAB, other C0 controls except CR/LF, DEL, and C1 controls
  U+0080 through U+009F are invalid. Other Unicode characters are accepted.
- Each blank physical record is **one empty field**. A final record terminator
  does not create another record. Empty files and BOM-only files are invalid.

The parser uses an explicit lexical state machine. It does not depend on
`csv.reader(strict=True)` to enforce this grammar.

## Limits and local-file boundary

| Resource | Inclusive maximum |
| --- | ---: |
| Input bytes (including BOM, quotes and endings) | 2,097,152 (2 MiB) |
| Logical records (including header) | 10,000 |
| Fields per record | 1,000 |
| Decoded field content re-encoded as UTF-8 | 65,536 bytes (64 KiB) |
| Findings | 10,000 |

Exceeding any limit invalidates the whole input; there is no partial report.
The bounded file is parsed in memory. Limits are constants, not CLI options.

Only a named local regular file is accepted. There is no stdin mode. URI schemes,
UNC paths (including mixed slash styles), Windows device namespaces/reserved
device names, and colon streams are rejected lexically before metadata or opening.
Windows absolute drive paths such as `C:\data\table.csv` are allowed; drive-relative
paths such as `C:table.csv` are rejected. Relative filenames beginning with `-`
must be given as `./-name.csv` (or an absolute path).

Symlink targets and mounted/network-backed filesystems are **not certified local**:
lexical path checks cannot determine their backing storage. The tool follows
ordinary filesystem resolution, verifies regular-file metadata before and after
opening, and opens only for reading. Filesystem access-time updates may occur.
It makes no network requests, starts no subprocesses, and writes no input/output
files. The test suite itself uses temporary fixtures and subprocesses.

## Verification and alternatives

Verified locally with Python 3.11.15 on Windows. Other platforms are intended but
not locally verified here. See [TESTING.md](TESTING.md) for executed checks and
[RESEARCH.md](RESEARCH.md) for scope, sources and alternatives. This tool is for
small shape checks; use Python's `csv` module for programmable dialect handling
or csvkit for a broader CSV toolkit. Neither is claimed inferior or benchmarked.

MIT license, copyright 2026 maomao-1937.
