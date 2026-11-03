#!/usr/bin/env python3

import os
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

def _remote_path(path):
    if not isinstance(path, str) or not path or path.startswith("-") or "\x00" in path:
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

        print(f"{source} -> {destination}")
        proc = subprocess.run(["scp"] + _host_options(known_hosts_path) + ["-i", private_key_path, "-r", source, destination]
                            , check=True
                            , stdout=subprocess.PIPE)
        eprint(proc.stdout.decode("utf-8"))

def sshRun(user, host, private_key_path, known_hosts_path, commands):
    if not isinstance(commands, list):
        raise ValueError("Expected 'commands' to be a list, found %s" % type(commands).__name__)
    
    print(commands)
    proc = subprocess.run(["ssh"] + _host_options(known_hosts_path) + ["-i", private_key_path, "%s@%s" % (user, host), "%s" % " && ".join(commands)]
                        , check=True
                        , stdout=subprocess.PIPE)
    eprint(proc.stdout.decode("utf-8"))
