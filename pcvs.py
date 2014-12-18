#!/usr/bin/env python

import logging
import os
import re
from subprocess import Popen, PIPE
from threading import Thread, Lock, Event
from time import sleep

logger = logging.getLogger(__name__)

# ### pluck
# Retrieve the selected keys from dictionary `d`
def pluck(d, *keys):
    return {key: d[key] for key in keys if key in d}

# ### TimeoutProcessWrapper
class TimeoutProcessWrapper(Thread):
    def __init__(self, proc, timeout, cmdline):
        super(TimeoutProcessWrapper, self).__init__()

        self._lock = Lock()
        self._proc = proc
        self._timeout = timeout
        self._timeout_event = Event()

        self.cmdline = cmdline

        self.daemon = True
        self.start()

    def __getattr__(self, attr):
        return getattr(self.proc, attr)

    @property
    def proc(self):
        with self._lock:
            return self._proc

    @property
    def timeout(self):
        with self._lock:
            return self._timeout

    @property
    def timed_out(self):
        if self.proc.poll() is None:
            return False

        return self._timeout_event.is_set()

    def run(self):
        sleep(self.timeout)
        if self.proc.poll() == None:
            self.proc.terminate()
            self._timeout_event.set()

    def __iter__(self):
        return iter(self.proc.stdout)


class SubprocessHelper(object):
    
    DEFAULT_OPTIONS = {
        "stderr": PIPE,
        "stdout": PIPE
    }

    def __init__(self, binary, *args, **kwargs):
        self.binary = binary
        self.argset = [(args, kwargs)]

    def __call__(self, *args, **kwargs):
        timeout, options, cmdline = self._resolve_cmdline(args, kwargs)
        proc = Popen(cmdline, **options)
        if timeout:
            return TimeoutProcessWrapper(proc, timeout, cmdline)
        
        proc.cmdline = cmdline
        return proc

    def __enter__(self):
        if all("__timeout" not in kwargs for _, kwargs in self.argset):
            raise ValueError("No timeout specified")

        self._proc = self()
        return self._proc

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._proc.poll() is None:
                self._proc.terminate()
                self._proc.wait()
        except AttributeError:
            pass

    def _resolve_cmdline(self, args, kwargs):
        top_args, top_kwargs = self.argset[-1]
        argset = self.argset[:-1] + [(top_args + args, dict(top_kwargs, **kwargs))]
        options = dict(self.DEFAULT_OPTIONS)
        timeout = None

        cmdline = [self.binary]
        for _args, _kwargs in argset:
            _kwargs = dict(_kwargs)

            if "__env" in _kwargs:
                options["env"] = _kwargs.pop("__env")

            if "__cwd" in _kwargs:
                options["cwd"] = _kwargs.pop("__cwd")

            if "__timeout" in _kwargs:
                timeout = _kwargs.pop("__timeout")

            _cwd = kwargs.pop("__cwd", None)
            if _cwd:
                options["cwd"] = _cwd

            _timeout = kwargs.pop("__timeout", None)

            for key, value in _kwargs.items():
                if value:
                    if key.startswith("__"):
                        param = "--{}".format(key[2:])
                    elif key.startswith("_"):
                        param = "-{}".format(key[1:])
                    elif len(key) == 1:
                        param = "-{}".format(key)
                    else:
                        param = "--{}".format(key)

                    cmdline.append(param)
                    if value is not True:
                        cmdline.append(str(value))

            cmdline.extend(_args)

        return timeout, options, cmdline

    def bake(self, *args, **kwargs):
        top_args, top_kwargs = self.argset[-1]
        instance = self.__class__(
                self.binary,
                *(top_args + args),
                **(dict(top_kwargs, **kwargs))
                )

        instance.argset = self.argset[:-1] + instance.argset
        return instance

    def after(self, *args, **kwargs):
        instance = self.bake()
        instance.argset.append((args, kwargs))
        return instance

    def get_cwd(self):
        _, options, _ = self._resolve_cmdline((), {})
        return options.get("cwd", None)

    def get_env(self):
        _, options, _ = self._resolve_cmdline((), {})
        return options.get("env", None)

CVS_ERROR_DEBUG_LOG = """\
Subprocess Error:
    Command: {cmdline}
    Returncode: {returncode}
    PID: {pid}
    CWD: {cwd}
    Environment: {env}
    STDERR: {stderr}\
"""

class CVSError(Exception):
    
    MESSAGE = "CVS {} failed with code {}"
    DEBUG = CVS_ERROR_DEBUG_LOG

    def __init__(self, subcommand, proc, cmd):
        msg = self.MESSAGE.format(subcommand, proc.returncode)
        super(CVSError, self).__init__(msg)
        self.data = {
            "cmdline": proc.cmdline,
            "returncode": proc.returncode,
            "pid": proc.pid,
            "cwd": cmd.get_cwd(),
            "env": pluck(cmd.get_env(), "CVSROOT", "CVS_RSH"),
            "stdout": cmd.stdout.read(),
            "stderr": cmd.stderr.read()
        }

        logger.error(msg)
        logger.debug(self.DEBUG.format(**self.data))

HEAD = None

### Repository
class Repository(object):

    CVS_LINE_PARSE_RE = re.compile(r"([UARMC?])\s+(.*)")

    # - `local_path` is the local root path of the CVS repository
    # - `module` is the remote module name of the CVS repository
    # - `env` (optional) as a dictionary containing (additional) environment variables to use
    #     (e.g. `CVSROOT` and `CVS_RSH`)
    # - `cvs_binary` (default: `"cvs"`) is the name of the binary to use for the CVS command
    # - `timeout` (default: `10`) is the duration before the CVS command is terminated
    def __init__(self, local_path, module, revision=HEAD,
            env=None, cvs_binary="cvs", timeout=10):
        self.root = os.path.abspath(local_path)
        self.module = module
        self.revision = revision
        self.env = env or os.environ
        self.cmd = SubprocessHelper(cvs_binary, q=True, 
                __timeout=timeout, __cwd=self.root, __env=self.env)

    def _run_cmd(self, subcommand, iter_lines=False, check_raise=False, *args, **kwargs):
        cmd = self.cmd.bake(subcommand).after(*args, **kwargs)
        with cmd as proc:
            if iter_lines:
                for line in proc:
                    parsed = self._parse_cvs_line(line)
                    if parsed:
                        yield parsed

        if check_raise and proc.returncode:
            raise CVSError(subcommand, proc, cmd)

    def _parse_cvs_line(self, line):
        match = self.CVS_LINE_PARSE_RE.match(line)
        if match:
            return match.groups()

    # ### checkout
    def checkout(self):
        cwd, base = os.path.split(self.root)
        return self._run_cmd("checkout", True, True,
                self.module, d=base, __cwd=cwd, r=self.revision)

    # ### update
    def update(self, clear=False):
        return self._run_cmd("update", True, True,
                A=True, C=clear, r=self.revision)

    # ### status
    def status(self):
        return self._run_cmd("update", True, True,
                A=True, n=True, r= self.revision)


