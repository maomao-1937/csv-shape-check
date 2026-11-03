# Research and scope

Reviewed 2026-11-03. The implementation is original project code; no upstream
implementation was copied and this project is not affiliated with the sources.

## Source-backed facts

- [RFC 4180](https://www.rfc-editor.org/rfc/rfc4180), section 2, describes CRLF
  records, optional headers, comma separation, quoted fields and doubled quotes.
  It is an informational RFC. This project additionally accepts LF and UTF-8
  Unicode and defines blank-record/control-character behavior explicitly.
- [Python 3.11 csv documentation](https://docs.python.org/3.11/library/csv.html)
  documents dialects, reader/writer APIs, the `strict` option, and `newline=''`
  for file objects. Its reader recognizes CR and LF line endings independently
  of the writer's line terminator setting.
- [csvkit documentation](https://csvkit.readthedocs.io/en/latest/) describes a
  suite of CSV tools including conversion and analysis. Its documented defaults
  include dialect sniffing and type inference, which can be disabled.

## Design inference and tradeoffs

For a small automated shape gate, a fixed grammar and numeric-only JSON can be
easier to review and less likely to disclose cell contents in logs. That is a
design inference, not a measured user outcome or comprehensive privacy guarantee.
Counts and locations still reveal structural information. The strict grammar
deliberately rejects some files accepted by more flexible readers.

An explicit lexer makes the accepted language auditable, including rejection of
bare CR records and unquoted quotes. This is not a claim that Python's CSV module
is defective. The project tests its own policy instead of treating a `strict`
flag as a complete grammar specification.

## Fair alternatives

| Alternative | Good fit | Difference from this project |
| --- | --- | --- |
| Python standard-library `csv` | Scripts needing custom dialects, readers and writers | General parsing API; caller chooses reporting and limits |
| csvkit | Conversion, filtering, SQL-style analysis and broader CLI tasks | Larger feature set; not restricted to this small fixed profile |
| This project | Bounded local shape checks with count/index JSON | No conversion, semantic typing, repair, or dialect discovery |

No competitor installation, performance benchmark, user study, or adoption claim
was made. No evidence establishes market demand or security certification.
