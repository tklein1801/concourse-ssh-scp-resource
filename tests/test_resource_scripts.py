import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.environ.get("RESOURCE_DIR", os.path.join(ROOT, "src"))


def run_script(name, args=None, input_text=""):
    return subprocess.run(
        [sys.executable, os.path.join(SRC, name)] + (args or []),
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


class ResourceScriptTests(unittest.TestCase):
    def test_check_returns_empty_versions(self):
        result = run_script("check")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), [])

    def test_in_returns_empty_version_and_metadata(self):
        result = run_script("in", ["/tmp"], "{}")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {"version": {}, "metadata": []})

    def test_out_returns_version(self):
        config = {
            "source": {
                "user": "alice",
                "host": "host",
                "private_key": "key",
                "known_hosts": "host ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n",
            },
            "params": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            result = run_script("out", [directory], json.dumps(config))

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertRegex(output["version"]["ref"], r"^out - .+")
            self.assertFalse(os.path.exists(os.path.join(directory, "id_rsa")))

    def test_out_with_files_and_commands_emits_only_json_on_stdout(self):
        config = {
            "source": {
                "user": "alice", "host": "host", "private_key": "key",
                "known_hosts": "host ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n",
            },
            "params": {"files": {"payload": "/remote/payload"}, "commands": ["true"]},
        }
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "payload"), "w") as payload:
                payload.write("data")
            with mock.patch("subprocess.run") as run:
                # Invoke the resource script with mocked SSH processes in-process.
                import runpy
                import shared
                run.return_value.stdout = b"process output"
                with mock.patch("sys.argv", ["out", directory]), mock.patch("sys.stdin", io.StringIO(json.dumps(config))), mock.patch("sys.stdout", io.StringIO()) as stdout, mock.patch("sys.stderr", io.StringIO()):
                    with self.assertRaises(SystemExit):
                        runpy.run_path(os.path.join(SRC, "out"), run_name="__main__")
                self.assertEqual(json.loads(stdout.getvalue()).keys(), {"version"})
                self.assertEqual(stdout.getvalue().count("\n"), 1)
                self.assertEqual(run.call_count, 2)

    def test_out_rejects_missing_required_configuration(self):
        result = run_script("out", ["/tmp"], "{}")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected to find 'source'", result.stderr)

    def test_out_requires_destination_argument(self):
        result = run_script("out", [], "{}")

        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
