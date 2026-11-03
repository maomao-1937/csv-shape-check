# Executed checks

Environment: Windows, Python 3.11.15. Executed locally on 2026-11-03 from this
repository's root. No other operating system was locally verified.

```sh
python -m unittest discover -s tests -v
```

Result: **31 unittest methods passed**. Subtests cover additional malformed CSV,
URI/UNC/device paths, invalid CLI arguments and closed stdout cases. The generated
round-trip method checks 100 deterministic CSV-writer-generated inputs, including
quoted commas, quotes, Unicode, CR, LF and CRLF cell contents.

Coverage includes exact decoded quoted content; BOM; blank records; header-only
and no-header files; deterministic JSON; exact duplicate/empty headers; width
findings; neutral invalid output; no path/header/cell leakage; all documented
resource limits at and over boundaries; read-only access; metadata failures;
local regular-file checks; URI/device/UNC rejection before metadata/opening; and
real subprocesses with stdout's pipe reader already closed. Closed-pipe tests
exercise help, successful JSON and invalid-input JSON, requiring exit 2 and empty
stderr (no traceback or interpreter shutdown exit 120).

The suite invokes the CLI by basename with its working directory set to the
repository root. It uses temporary test inputs outside the source directory.
Mocks are limited to resource limits, failure injection and proving forbidden
paths do not reach filesystem access. Real subprocesses verify CLI behavior.

## Runnable examples

`checks.json` is a list of argument arrays and expected exit codes. Executed each
with the current Python interpreter from this repository root:

| Command suffix after `python` | Observed exit |
| --- | ---: |
| `csv_shape_check.py examples/clean.csv` | 0 |
| `csv_shape_check.py examples/findings.csv` | 1 |
| `csv_shape_check.py examples/invalid.csv` | 2 |
| `csv_shape_check.py examples/no-header.csv --no-header` | 0 |
| `csv_shape_check.py examples/quoted.csv` | 0 |
| `csv_shape_check.py --help` | 0 |

All example commands produced empty stderr. The first five produced parseable
JSON, and help produced fixed usage text.

## Development evidence

Before implementation, the clean CLI test failed its exit-code assertion because
the CLI did not exist (observed 2, expected 0). A later path regression test
failed because `NUL .csv` reached metadata access; the device-name lexical check
was corrected and the suite passed. Raw RED/GREEN logs are retained outside this
publishable project by the batch builder. These logs are development evidence,
not a claim that every current test individually failed first.

No third-party dependencies, competitor benchmarks, production deployment,
user studies, or external network-backed filesystem checks were performed.
