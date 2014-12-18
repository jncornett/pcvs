
from subprocess import Popen, PIPE
from threading import Thread, Lock, Event
from time import sleep

class ValidationError(Exception):
    def __init__(self, msg, failed=None):
        super(ValidationError, self).__init__(msg)
        self.failed = failed or []


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
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        timeout, options, cmdline = self._resolve_cmdline(args, kwargs)
        proc = Popen(cmdline, **options)
        if timeout:
            return TimeoutProcessWrapper(proc, timeout, cmdline)
        
        proc.cmdline = cmdline
        return proc

    def _resolve_cmdline(self, args, kwargs):
        args = self.args + args
        kwargs = dict(self.kwargs, **kwargs)
        options = dict(self.DEFAULT_OPTIONS,
                env=kwargs.pop("__env", None),
                cwd=kwargs.pop("__cwd", None))
        timeout = kwargs.pop("__timeout", None)

        cmdline = [self.binary]
        for key, value in kwargs.items():
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

        cmdline.extend(args)
        return timeout, options, cmdline

    def bake(self, *args, **kwargs):
        return self.__class__(
                self.binary,
                *(self.args + args),
                **(dict(self.kwargs, **kwargs))
            )


class Option(object):
    def __init__(self, param, type=None, default=None):
        self.param = param
        self.type = type
        self.default = default

    def parse(self, value):
        if value is None:
            return self.default
        
        return self.type(value)


class Command(object):
    @classmethod
    def _parse_arguments(cls, arguments):
        parsed, unparsed = {}, dict(arguments)
        for key, option in cls.options.items():
            value = unparsed.pop(key, None)
            parsed_value = option.parse(value)
            if parsed_value:
                parsed[option.param] = parsed_value

        return parsed, unparsed



