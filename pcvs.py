#!/usr/bin/env python3
import os
import re
from collections import defaultdict
from shellwrap import SubprocessHelper, ProcessError

# ### subset
def subset(d, *keys):
    return {k: d[k] for k in keys if k in d}


# ### CVS Error
class CVSError(Exception):

    INVALID_REPO_MSG = "Not a valid CVS Repository: {why}"
    PERMISSIONS_MSG = "Invalid permissions: {why}"
    TIMEOUT_MSG = "CVS {command} timed out: {timeout}"
    CVS_ERROR_MSG = "CVS {command} exited with return code {code}: {stderr}"

    def __init__(self, msg, **kwargs):
        super(CVSError, self).__init__(msg)
        self.__dict__.update(kwargs)


# ### Repo
class Repo(object):

    CVS_STDOUT_RE = re.compile(r"([AUPMC?])\s+(.*?)\s*")

    def __init__(self, path, module=None, revision=None,
                 binary="cvs", env=None, timeout=None):
        self.root = path
        self._module = module
        self._revision = revision
        self._cvs = SubprocessHelper.create(
                binary,
                q=True,
                _env = env or subset(os.environ, "CVSROOT", "CVS_RSH"),
                _timeout = timeout)


    def _get_cvs_filename(self, name):
        return os.path.join(self.root, "CVS", name.capitalize())

    
    def _get_data(self, name):
        path = self._get_cvs_filename(name)
        try:
            with open(path, "rb") as f:
                return f.read().strip()
        except OSError as e:
            if isinstance(e, FileNotFoundError):
                msg = CVSError.INVALID_REPO_MSG.format(
                        why="Data file not found")
            elif isinstance(e, IsADirectoryError):
                msg = CVSError.INVALID_REPO_MSG.format(
                        why="Path is a directory")
            elif isinstance(e, PermissionError):
                msg = CVSError.PERMISSIONS_MSG.format(
                        why="Can't access path")
            else:
                raise e

            raise CVSError(msg, path=path)


    def _stat_file(self, name):
        path = self._get_cvs_filename(name)
        try:
            return os.stat(path)
        except FileNotFoundError:
            raise CVSError(
                    CVSError.INVALID_REPO_MSG.format(
                        why="Data file not found"),
                    path=path)


    def _parse_cvs_out(self, f):
        changes = defaultdict(list)
        for line in f:
            match = self.CVS_STDOUT_RE.match(line)
            if match:
                action, filename = match.groups()
                changes[action].append(filename)

        return dict(changes)


    def _include_revision(self, d=None):
        if d is None:
            d = {}

        revision = self.revision
        if revision:
            d["r"] = revision

        return d


    def _handle_process(self, proc, command):
        try:
            proc.check()
            return self._parse_cvs_out(proc.stdout)
        except ProcessError as e:
            if e.data.get("timed_out", False):
                msg = CVSError.TIMEOUT_MSG.format(
                        command=command,
                        timeout=e.data["timeout"])
            else:
                msg = CVSError.CVS_ERROR_MSG.format(
                        command=command,
                        code=e.data["returncode"],
                        stderr=e.data["stderr"])

            raise CVSError(msg, data=e.data)


    # #### module
    @property
    def module(self):
        return self._module or self._get_data("repository")


    # #### revision
    @property
    def revision(self):
        return self._revision or self._get_data("tag")[1:]


    # #### last_update
    @property
    def last_update(self):
        return self._stat_file("entries").st_atime


    # #### requires_update
    def requires_update(self, interval):
        return self.last_update + interval < time.time()


    # ### checkout
    def checkout(self):
        cwd, d = os.path.split(self.root)
        params = self._include_revision({"d": d})
        checkout = self._cvs.subcommand("checkout", self.module, **params)
        return self._handle_process(checkout.call(_cwd=cwd), "checkout")


    # ### update
    def update(self, clear=True):
        params = self._include_revision({"C": clear})
        update = self._cvs.subcommand("update", **params)
        return self._handle_process(checkout.call(_cwd=cwd), "update")
