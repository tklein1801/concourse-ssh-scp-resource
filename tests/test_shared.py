import os
import sys
import tempfile
import unittest
from unittest import mock

RESOURCE_DIR = os.environ.get(
    "RESOURCE_DIR",
    os.path.join(os.path.dirname(__file__), "..", "src"),
)
sys.path.insert(0, RESOURCE_DIR)

import shared


class ValidateSchemaTests(unittest.TestCase):
    def test_accepts_matching_nested_values(self):
        shared.validate_schema(
            {"source": {"user": "alice"}, "params": {}},
            {"source": {"user": ""}, "params": {}},
        )

    def test_rejects_missing_nested_value(self):
        with self.assertRaisesRegex(ValueError, "source.user"):
            shared.validate_schema({"source": {}}, {"source": {"user": ""}})

    def test_rejects_wrong_type(self):
        with self.assertRaisesRegex(ValueError, "Expected 'user' to be str, found int"):
            shared.validate_schema({"user": 7}, {"user": ""})


class PrivateKeyTests(unittest.TestCase):
    def test_writes_key_with_restricted_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = shared.write_private_key(directory, "test-key")

            with open(path) as key_file:
                self.assertEqual(key_file.read(), "test-key")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class TransferTests(unittest.TestCase):
    @mock.patch("shared.subprocess.run")
    def test_scp_to_builds_remote_destination(self, run):
        run.return_value.stdout = b"copied"
        shared.scpTo("alice", "host", "/key", "/work", {"artifact": "/remote/artifact"})

        args, kwargs = run.call_args
        self.assertEqual(args[0], [
            "scp", "-oStrictHostKeyChecking=no", "-i", "/key", "-r",
            "/work/artifact", "alice@host:/remote/artifact",
        ])
        self.assertTrue(kwargs["check"])

    @mock.patch("shared.subprocess.run")
    def test_scp_from_builds_local_destination(self, run):
        run.return_value.stdout = b"copied"
        shared.scpFrom("alice", "host", "/key", "/work", {"/remote/file": "file"})

        args, _ = run.call_args
        self.assertEqual(args[0][-2:], ["alice@host:/remote/file", "/work/file"])

    def test_scp_rejects_non_mapping_files(self):
        with self.assertRaisesRegex(ValueError, "Expected 'files' to be a dict"):
            shared.scpTo("alice", "host", "/key", "/work", [])

    @mock.patch("shared.subprocess.run")
    def test_ssh_joins_commands_and_checks_exit_status(self, run):
        run.return_value.stdout = b"done"
        shared.sshRun("alice", "host", "/key", ["first", "second"])

        args, kwargs = run.call_args
        self.assertEqual(args[0][-2:], ["alice@host", "first && second"])
        self.assertTrue(kwargs["check"])

    def test_ssh_rejects_non_list_commands(self):
        with self.assertRaisesRegex(ValueError, "Expected 'commands' to be a list"):
            shared.sshRun("alice", "host", "/key", "command")


if __name__ == "__main__":
    unittest.main()
