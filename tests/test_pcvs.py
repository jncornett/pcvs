from unittest import TestCase
import contextlib
import logging

from pcvs import Repo, CVSError
from shellwrap import ProcessWrapper, ProcessWrapperWithTimeout, \
        SubprocessHelper

logger = logging.getLogger("test")

@contextlib.contextmanager
def patch(obj, attr, patch):
    old_attr = getattr(obj, attr)
    setattr(obj, attr, patch)
    yield
    setattr(obj, attr, old_attr)


class TestRepo(TestCase):
    def test_get_cvs_filename(self):
        r = Repo("foo", "bar", "buzz")
        self.assertEqual(r._get_cvs_filename("entries"), "foo/CVS/Entries")

    def test_handle_process(self):
        r = Repo("a")
        sh = SubprocessHelper.create("sleep")

        p1 = sh.call("0.05")
        rv = r._handle_process(p1, "foo")
        self.assertEquals(rv, {})

        p2 = sh.call("0.1", _timeout=0.05)
        self.assertRaises(CVSError, r._handle_process, p2, "foo")

        sh2 = SubprocessHelper.create("ls")
        p3 = sh2.call("doesntexistfoo")
        self.assertRaises(CVSError, r._handle_process, p3, "foo")

