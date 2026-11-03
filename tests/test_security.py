import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

import sys
resource_dir = os.environ.get(
    "RESOURCE_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")),
)
sys.path.insert(0, resource_dir)
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
        with self.assertRaises(ValueError):
            shared._remote_path("other-host:/tmp/file")

    def test_upload_directory_rejects_symlink_before_scp(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = os.path.join(directory, "root")
            os.mkdir(root)
            with open(os.path.join(outside, "secret"), "w") as secret:
                secret.write("secret")
            os.symlink(os.path.join(outside, "secret"), os.path.join(root, "link"))
            with mock.patch.object(shared.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "must not contain symlinks"):
                    shared.scpTo("user", "host", "/key", "/known_hosts", directory,
                                 {"root": "/remote/root"})
            run.assert_not_called()

    def test_upload_status_and_commands_use_stderr(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "file"), "w") as output:
                output.write("payload")
            with mock.patch.object(shared.subprocess, "run", return_value=mock.Mock(stdout=b"ok")):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    shared.scpTo("user", "host", "/key", "/known_hosts", directory,
                                 {"file": "/remote/file"})
                    shared.sshRun("user", "host", "/key", "/known_hosts", ["true"])
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(" -> ", stderr.getvalue())
        self.assertIn("['true']", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
