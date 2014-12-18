from unittest import TestCase
import subprocess
import time

import pcvs

class TestTimeoutProcessWrapper(TestCase):
    def setUp(self):
        self.a_long_time = 0.1
        self.a_short_time = 0.05
        self.stdout_lines = ["One\n", "Two\n", "Three\n"]
        self.long_sleep_cmdline = [
                "sleep", str(self.a_long_time)]
        self.short_sleep_cmdline = [
                "sleep", str(self.a_short_time)]
        self.stdout_test_cmdline = [
                "echo", "".join(self.stdout_lines).rstrip()]

    def test_both(self):
        p = subprocess.Popen(self.stdout_test_cmdline,
                stdout=subprocess.PIPE)
        tpw = pcvs.TimeoutProcessWrapper(p,
                self.a_short_time, self.stdout_test_cmdline)
        tpw.wait() # Make sure the process completes
        self.assertEquals(tpw.cmdline, self.stdout_test_cmdline)

        # This test depends on threading
        self.assertEquals(list(tpw), self.stdout_lines)

    def test_with_timeout(self):
        cmdline = self.long_sleep_cmdline
        timeout = self.a_short_time

        p = subprocess.Popen(cmdline)
        tpw = pcvs.TimeoutProcessWrapper(p, timeout, cmdline)
        self.assertFalse(tpw.timed_out)
        tpw.wait()

        # These 2 asserts test threading
        self.assertTrue(tpw.timed_out)
        self.assertTrue(tpw.returncode < 0,
                "If the process timed out and was terminated, "
                "expect a negative returncode value")

    def test_without_timeout(self):
        cmdline = self.short_sleep_cmdline
        timeout = self.a_long_time

        p = subprocess.Popen(cmdline)
        tpw = pcvs.TimeoutProcessWrapper(p, timeout, cmdline)
        tpw.wait()

        # This 2 asserts test threading
        self.assertFalse(tpw.timed_out)
        self.assertEquals(tpw.returncode, 0)

class TestSubprocessHelper(TestCase):
    def setUp(self):
        self.def_options = {
            "env": None,
            "cwd": None,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE
            }

    def test_bake(self):
        sh = pcvs.SubprocessHelper("my_binary")
        baked = sh.bake("one", two="four")
        self.assertEquals(baked.args, ("one",))
        self.assertEquals(baked.kwargs, {"two": "four"})

    def test__resolve_cmdline(self):
        sh = pcvs.SubprocessHelper("my_binary")
        (timeout, 
         options, 
         cmdline) = sh._resolve_cmdline(
                 ("one",), {"two": "four"})

        self.assertIsNone(timeout)
        self.assertEquals(options, self.def_options)
        self.assertEquals(cmdline, 
                ["my_binary", "--two", "four", "one"],
                "Keyword arguments should appear before "
                "positional arguments by default")
        
        (_, options, cmdline) = sh._resolve_cmdline(
                (), {"__env": "foo"})

        self.assertIn("env", options)
        self.assertEqual(options["env"], "foo")
        self.assertEquals(cmdline, ["my_binary"])

        (_, _, cmdline) = sh._resolve_cmdline(
                (), {"__f": True, "b": 4, "c": False})
        self.assertEqual(len(cmdline), 4)
        self.assertEqual(cmdline[0], "my_binary")
        self.assertIn("--f", cmdline)
        self.assertIn("-b", cmdline)
        self.assertEquals(cmdline[cmdline.index("-b"):],
                ["-b", "4"])

        (timeout, options, cmdline) = sh._resolve_cmdline(
                (), {"__timeout": 10})

        self.assertEqual(timeout, 10)
        self.assertEquals(options, self.def_options)
        self.assertEquals(cmdline, ["my_binary"])


    def test___call__(self):
        sh = pcvs.SubprocessHelper("echo", "one")
        p = sh("two")
        p.wait()
        self.assertEquals(p.cmdline, 
                ["echo", "one", "two"])
        self.assertEquals(list(p.stdout), ["one two\n"])

    def test_timeout(self):
        p = pcvs.SubprocessHelper("echo", __timeout=0.05)()
        self.assertIsInstance(p, pcvs.TimeoutProcessWrapper)

        # These 2 asserts test threading
        self.assertTrue(p.is_alive())
        time.sleep(0.1)
        self.assertFalse(p.is_alive())

        self.assertEqual(p._timeout, 0.05)
        p.wait()
