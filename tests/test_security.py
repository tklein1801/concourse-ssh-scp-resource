import os
import tempfile
import unittest
from unittest import mock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import shared


class SecurityTests(unittest.TestCase):
    def test_secret_file_is_exclusive_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = shared.write_secret(directory, "id_rsa", "secret")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                shared.write_secret(directory, "id_rsa", "replacement")

    def test_ssh_requires_strict_known_hosts(self):
        with mock.patch.object(shared.subprocess, "run") as run:
            shared.sshRun("user", "host", "/key", "/known_hosts", ["true"])
            args = run.call_args[0][0]
            self.assertIn("-oStrictHostKeyChecking=yes", args)
            self.assertIn("-oUserKnownHostsFile=/known_hosts", args)
            self.assertIn("-oGlobalKnownHostsFile=/dev/null", args)

    def test_local_source_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                shared._local_source(directory, "../outside")

    def test_remote_path_is_passed_as_sftp_path(self):
        self.assertEqual(shared._remote_path("a; touch /tmp/pwned"), "a; touch /tmp/pwned")
        with self.assertRaises(ValueError):
            shared._remote_path("-oProxyCommand=evil")


if __name__ == "__main__":
    unittest.main()
