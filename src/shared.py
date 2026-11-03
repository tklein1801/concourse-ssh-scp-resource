#!/usr/bin/env python3

import os
import shutil
import stat
import subprocess
import sys
import tempfile

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def validate_schema(target, schema, prefix=""):
    for (key, value) in schema.items():
        if not key in target:
            raise ValueError("Expected to find '%s%s' value in config" % (prefix, key))

        if not type(value) == type(target[key]):
            raise ValueError("Expected '%s%s' to be %s, found %s" % (prefix, key, type(value).__name__, type(target[key]).__name__))

        if isinstance(value, dict):
            validate_schema(target[key], schema[key], "%s." % key)

def write_secret(directory, name, contents):
    secret_path = os.path.join(directory, name)
    fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as secret_file:
        secret_file.write(contents)
    return secret_path

def _host_options(known_hosts_path):
    return ["-oStrictHostKeyChecking=yes", "-oUserKnownHostsFile=%s" % known_hosts_path,
            "-oGlobalKnownHostsFile=/dev/null", "-oBatchMode=yes"]

def _local_source(root, source_file):
    if not isinstance(source_file, str) or os.path.isabs(source_file):
        raise ValueError("SCP source paths must be relative to the resource directory")
    root = os.path.realpath(root)
    source = os.path.realpath(os.path.join(root, source_file))
    if os.path.commonpath([root, source]) != root:
        raise ValueError("SCP source path escapes the resource directory")
    current = root
    for part in source_file.split(os.sep):
        current = os.path.join(current, part)
        if os.path.islink(current):
            resolved = os.path.realpath(current)
            if os.path.commonpath([root, resolved]) != root:
                raise ValueError("SCP source symlink escapes the resource directory")
    return source

def _copy_file_descriptor(source_fd, destination):
    with os.fdopen(os.dup(source_fd), "rb") as source_file, open(destination, "wb") as target_file:
        shutil.copyfileobj(source_file, target_file)

def _copy_tree_descriptor(source_fd, destination):
    os.mkdir(destination)
    for name in os.listdir(source_fd):
        info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        target = os.path.join(destination, name)
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("SCP source directory must not contain symlinks")
        if stat.S_ISDIR(info.st_mode):
            child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=source_fd)
            try:
                _copy_tree_descriptor(child_fd, target)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(info.st_mode):
            child_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source_fd)
            try:
                opened = os.fstat(child_fd)
                if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError("SCP source changed during upload snapshot")
                _copy_file_descriptor(child_fd, target)
            finally:
                os.close(child_fd)
        else:
            raise ValueError("SCP source directory contains an unsupported file type")

def _safe_upload_copy(root, source_file):
    """Snapshot a regular file or symlink-free tree for an SCP upload."""
    temporary_directory = tempfile.mkdtemp(prefix="concourse-upload-")
    snapshot = os.path.join(temporary_directory, "upload")
    try:
        root_fd = os.open(os.path.realpath(root), os.O_RDONLY | os.O_DIRECTORY)
        source_fd = root_fd
        try:
            parts = source_file.split(os.sep)
            for part in parts[:-1]:
                if part in ("", ".", ".."):
                    raise ValueError("Invalid SCP source path")
                child_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=source_fd)
                if source_fd != root_fd:
                    os.close(source_fd)
                source_fd = child_fd
            name = parts[-1]
            if name in ("", ".", ".."):
                raise ValueError("Invalid SCP source path")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            try:
                source_item_fd = os.open(name, flags | os.O_DIRECTORY, dir_fd=source_fd)
            except NotADirectoryError:
                source_item_fd = os.open(name, flags, dir_fd=source_fd)
                try:
                    if not stat.S_ISREG(os.fstat(source_item_fd).st_mode):
                        raise ValueError("SCP source must be a regular file or directory")
                    _copy_file_descriptor(source_item_fd, snapshot)
                finally:
                    os.close(source_item_fd)
            else:
                try:
                    _copy_tree_descriptor(source_item_fd, snapshot)
                finally:
                    os.close(source_item_fd)
        finally:
            if source_fd != root_fd:
                os.close(source_fd)
            os.close(root_fd)
        return temporary_directory, snapshot
    except BaseException:
        shutil.rmtree(temporary_directory)
        raise

def _remote_path(path):
    if not isinstance(path, str) or not path or path.startswith("-") or ":" in path or "\x00" in path:
        raise ValueError("Invalid remote SCP path")
    # OpenSSH's default SFTP transport passes paths without invoking a remote shell.
    return path

def scpTo(user, host, private_key_path, known_hosts_path, path, files):
    return _scp(user, host, private_key_path, known_hosts_path, path, files, True)

def scpFrom(user, host, private_key_path, known_hosts_path, path, files):
    return _scp(user, host, private_key_path, known_hosts_path, path, files, False)

def _scp(user, host, private_key_path, known_hosts_path, path, files, toRemote):
    if not isinstance(files, dict):
        raise ValueError("Expected 'files' to be a dict, found %s" % type(files).__name__)

    for (source_file, destination_file) in files.items():
        source = _local_source(path, source_file) if toRemote else "%s@%s:%s" % (user, host, _remote_path(source_file))
        destination = "%s@%s:%s" % (user, host, _remote_path(destination_file)) if toRemote else _local_source(path, destination_file)

        if toRemote:
            temporary_directory, safe_source = _safe_upload_copy(path, source_file)
            try:
                eprint(f"{source} -> {destination}")
                proc = subprocess.run(["scp"] + _host_options(known_hosts_path) + ["-i", private_key_path, "-r", safe_source, destination]
                                    , check=True
                                    , stdout=subprocess.PIPE)
                eprint(proc.stdout.decode("utf-8"))
            finally:
                shutil.rmtree(temporary_directory)
        else:
            eprint(f"{source} -> {destination}")
            proc = subprocess.run(["scp"] + _host_options(known_hosts_path) + ["-i", private_key_path, "-r", source, destination]
                                , check=True
                                , stdout=subprocess.PIPE)
            eprint(proc.stdout.decode("utf-8"))

def sshRun(user, host, private_key_path, known_hosts_path, commands):
    if not isinstance(commands, list):
        raise ValueError("Expected 'commands' to be a list, found %s" % type(commands).__name__)
    
    eprint(commands)
    proc = subprocess.run(["ssh"] + _host_options(known_hosts_path) + ["-i", private_key_path, "%s@%s" % (user, host), "%s" % " && ".join(commands)]
                        , check=True
                        , stdout=subprocess.PIPE)
    eprint(proc.stdout.decode("utf-8"))
