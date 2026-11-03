import json
import importlib.util
import io
import csv
import os
import pathlib
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]


def implementation():
    spec = importlib.util.spec_from_file_location("csv_shape_check", ROOT / "csv_shape_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShapeTests(unittest.TestCase):
    def setUp(self):
        self.tool = implementation()

    def test_quoted_fields_preserve_exact_content(self):
        raw = b'"a,b","a""b","a\r\nb","a\nb"\r\n'
        self.assertEqual(self.tool.parse(raw), [["a,b", 'a"b', "a\r\nb", "a\nb"]])

    def test_bom_and_unicode(self):
        self.assertEqual(self.tool.parse(b'\xef\xbb\xbf' + '名字,值\n猫,一'.encode()), [["名字", "值"], ["猫", "一"]])

    def test_blank_records_are_single_empty_fields(self):
        self.assertEqual(self.tool.parse(b'\n\r\n""\n'), [[""], [""], [""]])

    def test_trailing_delimiter_and_no_final_newline(self):
        self.assertEqual(self.tool.parse(b'a,\n,b'), [["a", ""], ["", "b"]])

    def test_malformed_lexical_inputs(self):
        for raw in [b'', b'\xef\xbb\xbf', b'a"b', b'"a"x', b'"a" ', b'"abc', b'a\rb', b'a\r', b'\xff', b'a\x00b', b'a\tb', b'a\x1fb', b'a\x7fb', 'a\u0085b'.encode()]:
            with self.subTest(raw=raw), self.assertRaises(self.tool.InvalidInput):
                self.tool.parse(raw)

    def test_no_header_uses_first_width(self):
        result = self.tool.inspect_bytes(b'a,a\nb\n', no_header=True)
        self.assertEqual(result['counts'], {'records': 2, 'header': 0, 'data': 2, 'columns': 2})
        self.assertEqual(result['findings'], [{'code': 'WIDTH_MISMATCH', 'record': 2, 'expected': 2, 'actual': 1}])

    def test_exact_header_duplicates_and_empty_names(self):
        result = self.tool.inspect_bytes(b'a,a,,A, a\n1,2,3,4,5\n')
        self.assertEqual(result['findings'], [
            {'code': 'DUPLICATE_HEADER', 'record': 1, 'column': 2, 'first_column': 1},
            {'code': 'EMPTY_HEADER', 'record': 1, 'column': 3},
        ])

    def test_header_only_is_clean(self):
        self.assertEqual(self.tool.inspect_bytes(b'a,b')['counts']['data'], 0)

    def test_byte_limit(self):
        with mock.patch.object(self.tool, 'MAX_BYTES', 3):
            self.assertEqual(self.tool.parse(b'a,b'), [['a', 'b']])
            with self.assertRaises(self.tool.InvalidInput):
                self.tool.parse(b'a,bb')

    def test_record_limit(self):
        with mock.patch.object(self.tool, 'MAX_RECORDS', 2):
            self.assertEqual(len(self.tool.parse(b'a\nb\n')), 2)
            with self.assertRaises(self.tool.InvalidInput):
                self.tool.parse(b'a\nb\nc')

    def test_field_limit(self):
        with mock.patch.object(self.tool, 'MAX_FIELDS', 2):
            self.assertEqual(self.tool.parse(b'a,b'), [['a', 'b']])
            with self.assertRaises(self.tool.InvalidInput):
                self.tool.parse(b'a,b,c')

    def test_cell_limit_counts_utf8_decoded_content(self):
        with mock.patch.object(self.tool, 'MAX_CELL_BYTES', 4):
            self.assertEqual(self.tool.parse('"éé"'.encode()), [['éé']])
            with self.assertRaises(self.tool.InvalidInput):
                self.tool.parse('"ééa"'.encode())

    def test_finding_limit(self):
        with mock.patch.object(self.tool, 'MAX_FINDINGS', 1):
            self.assertEqual(len(self.tool.inspect_bytes(b'a,a')['findings']), 1)
            with self.assertRaises(self.tool.InvalidInput):
                self.tool.inspect_bytes(b'a,a,a')

    def test_real_limits_and_cells(self):
        self.assertEqual(len(self.tool.parse(b'a' * 65536)[0][0]), 65536)
        with self.assertRaises(self.tool.InvalidInput):
            self.tool.parse(b'a' * 65537)
        self.assertEqual(len(self.tool.parse(b'x\n' * 10000)), 10000)
        with self.assertRaises(self.tool.InvalidInput):
            self.tool.parse(b'x\n' * 10001)
        self.assertEqual(len(self.tool.parse(b',' * 999)[0]), 1000)
        with self.assertRaises(self.tool.InvalidInput):
            self.tool.parse(b',' * 1000)

    def test_actual_byte_and_finding_boundaries(self):
        raw = (b'a' * 65535 + b'\n') * 32
        self.assertEqual(len(raw), 2 * 1024 * 1024)
        self.assertEqual(len(self.tool.parse(raw)), 32)
        with self.assertRaises(self.tool.InvalidInput):
            self.tool.parse(raw + b'\n')
        raw = b',' * 999 + b'\n' + b'x\n' * 8001
        self.assertEqual(len(self.tool.inspect_bytes(raw)['findings']), 10000)
        with self.assertRaises(self.tool.InvalidInput):
            self.tool.inspect_bytes(raw + b'x\n')

    def test_writer_generated_round_trips(self):
        generator = random.Random(1937)
        for _ in range(100):
            rows = [[''.join(generator.choice('ab,\"\r\n猫') for _ in range(generator.randrange(8))) for _ in range(3)] for _ in range(4)]
            stream = io.StringIO(newline='')
            csv.writer(stream, lineterminator='\r\n').writerows(rows)
            self.assertEqual(self.tool.parse(stream.getvalue().encode()), rows)

    def test_metadata_error_is_neutral(self):
        with mock.patch.object(self.tool.os, 'stat', side_effect=PermissionError('PRIVATE')):
            with self.assertRaises(self.tool.InvalidInput) as caught:
                self.tool.read_local('local.csv')
        self.assertEqual(str(caught.exception), '')

    def test_unsafe_paths_rejected_before_metadata_or_open(self):
        paths = ['https://example.test/x.csv', 'file:///tmp/x', 's3:x', '//host/x', '\\\\host\\x', '\\/host/x', '/\\host/x', '\\\\?\\C:\\x', '\\\\.\\NUL', '\\??\\C:\\x', 'NUL', 'aux.csv', 'C:relative.csv', 'C:\\x:stream']
        for path in paths:
            with self.subTest(path=path), mock.patch.object(self.tool.os, 'stat', side_effect=AssertionError('metadata accessed')), mock.patch.object(self.tool.os, 'open', side_effect=AssertionError('opened')):
                with self.assertRaises(self.tool.InvalidInput):
                    self.tool.read_local(path)

    def test_drive_path_is_lexically_allowed(self):
        with mock.patch.object(self.tool.os, 'stat', side_effect=FileNotFoundError) as stat:
            with self.assertRaises(self.tool.InvalidInput):
                self.tool.read_local('C:\\local\\data.csv')
            stat.assert_called_once()

    def test_windows_device_stem_with_space_is_rejected_before_access(self):
        with mock.patch.object(self.tool.os, 'stat', side_effect=AssertionError('metadata accessed')):
            with self.assertRaises(self.tool.InvalidInput):
                self.tool.read_local('NUL .csv')

    def test_directory_is_invalid(self):
        with self.assertRaises(self.tool.InvalidInput):
            self.tool.read_local(str(ROOT))

    def test_read_only_and_bounded_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'private.csv'
            path.write_bytes(b'a,b\n1,2\n')
            before = path.stat()
            with mock.patch.object(self.tool.os, 'open', wraps=os.open) as opened:
                self.assertEqual(self.tool.read_local(str(path)), b'a,b\n1,2\n')
                self.assertEqual(opened.call_args.args[1] & (os.O_WRONLY | os.O_RDWR), 0)
            self.assertEqual(path.read_bytes(), b'a,b\n1,2\n')
            self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
            with mock.patch.object(self.tool, 'MAX_BYTES', 4), self.assertRaises(self.tool.InvalidInput):
                self.tool.read_local(str(path))

    def test_closed_output_stream_neutral_exit(self):
        for exception in [BrokenPipeError(), OSError(), ValueError()]:
            sink = mock.Mock()
            sink.write.side_effect = exception
            with mock.patch.object(self.tool.sys, 'stdout', sink):
                self.assertEqual(self.tool.main(['--help']), 2)


class CommandTests(unittest.TestCase):
    def run_data(self, raw, *args):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'SECRET_PATH.csv'
            path.write_bytes(raw)
            return subprocess.run([sys.executable, 'csv_shape_check.py', str(path), *args], cwd=ROOT, capture_output=True, check=False)

    def test_clean_csv_command_has_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "sample.csv"
            path.write_bytes(b"name,value\nalpha,1\n")
            result = subprocess.run(
                [sys.executable, "csv_shape_check.py", str(path)],
                cwd=ROOT, capture_output=True, check=False,
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout), {
            "status": "clean", "counts": {
                "records": 2, "header": 1, "data": 1, "columns": 2,
            }, "findings": [],
        })

    def test_findings_exit_and_privacy(self):
        result = self.run_data(b'SECRET_HEADER,SECRET_HEADER\nSECRET_CELL\n')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, b'')
        self.assertNotIn(b'SECRET', result.stdout)
        self.assertEqual(len(json.loads(result.stdout)['findings']), 2)

    def test_output_is_deterministic(self):
        raw = b'a,a\n1\n'
        self.assertEqual(self.run_data(raw).stdout, self.run_data(raw).stdout)

    def test_invalid_exit_is_neutral(self):
        for raw in [b'', b'PRIVATE"BAD', b'\xff']:
            with self.subTest(raw=raw):
                result = self.run_data(raw)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, b'')
                self.assertEqual(json.loads(result.stdout), {'status': 'invalid', 'code': 'INVALID_INPUT'})

    def test_no_header_cli(self):
        result = self.run_data(b'x,x\ny,z', '--no-header')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['counts']['header'], 0)

    def test_usage_paths_and_missing_files_never_echo(self):
        for args in [[], ['--PRIVATE'], ['https://PRIVATE/x'], ['PRIVATE_MISSING.csv'], ['--help', 'PRIVATE'], ['x', 'y'], ['--no-header', '--no-header', 'x']]:
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, 'csv_shape_check.py', *args], cwd=ROOT, capture_output=True, check=False)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, b'')
                self.assertNotIn(b'PRIVATE', result.stdout)

    def test_help(self):
        result = subprocess.run([sys.executable, 'csv_shape_check.py', '--help'], cwd=ROOT, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'--no-header', result.stdout)
        self.assertEqual(result.stderr, b'')

    def test_real_closed_pipe_including_help(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'data.csv'
            path.write_bytes(b'a,b\n1,2\n')
            for args in [['--help'], [str(path)], ['missing.csv']]:
                with self.subTest(args=args):
                    read_fd, write_fd = os.pipe()
                    os.close(read_fd)
                    try:
                        process = subprocess.Popen([sys.executable, 'csv_shape_check.py', *args], cwd=ROOT, stdout=write_fd, stderr=subprocess.PIPE)
                    finally:
                        os.close(write_fd)
                    _, stderr = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 2)
                    self.assertEqual(stderr, b'')


if __name__ == "__main__":
    unittest.main()
