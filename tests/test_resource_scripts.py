import json
import os
import subprocess
import sys
import tempfile
import unittest


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
            "source": {"user": "alice", "host": "host", "private_key": "key"},
            "params": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            result = run_script("out", [directory], json.dumps(config))
            key_path = os.path.join(directory, "id_rsa")

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertRegex(output["version"]["ref"], r"^out - .+")
            self.assertEqual(os.stat(key_path).st_mode & 0o777, 0o600)

    def test_out_rejects_missing_required_configuration(self):
        result = run_script("out", ["/tmp"], "{}")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected to find 'source'", result.stderr)

    def test_out_requires_destination_argument(self):
        result = run_script("out", [], "{}")

        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
