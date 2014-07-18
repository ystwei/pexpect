#!/usr/bin/env python
'''
PEXPECT LICENSE

    This license is approved by the OSI and FSF as GPL-compatible.
        http://opensource.org/licenses/isc-license.txt

    Copyright (c) 2012, Noah Spurrier <noah@noah.org>
    PERMISSION TO USE, COPY, MODIFY, AND/OR DISTRIBUTE THIS SOFTWARE FOR ANY
    PURPOSE WITH OR WITHOUT FEE IS HEREBY GRANTED, PROVIDED THAT THE ABOVE
    COPYRIGHT NOTICE AND THIS PERMISSION NOTICE APPEAR IN ALL COPIES.
    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
    WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
    MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
    ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
    WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
    ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
    OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

'''
import unittest
import sys
import re
import signal
import time
import tempfile
import os

import pexpect
from . import PexpectTestCase

# the program cat(1) may display ^D\x08\x08 when \x04 (EOF, Ctrl-D) is sent
_CAT_EOF = b'^D\x08\x08'


if (sys.version_info[0] >= 3):
    def _u(s):
        return s.decode('utf-8')
else:
    def _u(s):
        return s


class TestCaseMisc(PexpectTestCase.PexpectTestCase):

    def test_isatty(self):
        " Test isatty() is True after spawning process on most platforms. "
        child = pexpect.spawn('cat')
        if not child.isatty() and sys.platform.lower().startswith('sunos'):
            if hasattr(unittest, 'SkipTest'):
                raise unittest.SkipTest("Not supported on this platform.")
            return 'skip'
        assert child.isatty()

    def test_read(self):
        " Test spawn.read by calls of various size. "
        child = pexpect.spawn('cat')
        child.sendline("abc")
        child.sendeof()
        self.assertEqual(child.read(0), b'')
        self.assertEqual(child.read(1), b'a')
        self.assertEqual(child.read(1), b'b')
        self.assertEqual(child.read(1), b'c')
        self.assertEqual(child.read(2), b'\r\n')
        remaining = child.read().replace(_CAT_EOF, b'')
        self.assertEqual(remaining, b'abc\r\n')

    def test_readline_bin_echo(self):
        " Test spawn('echo'). "
        # given,
        child = pexpect.spawn('echo', ['alpha', 'beta'])

        # exercise,
        assert child.readline() == b'alpha beta' + child.crlf

    def test_readline(self):
        " Test spawn.readline(). "
        # when argument 0 is sent, nothing is returned.
        # Otherwise the argument value is meaningless.
        child = pexpect.spawn('cat', echo=False)
        child.sendline("alpha")
        child.sendline("beta")
        child.sendline("gamma")
        child.sendline("delta")
        child.sendeof()
        assert child.readline(0) == b''
        assert child.readline().rstrip() == b'alpha'
        assert child.readline(1).rstrip() == b'beta'
        assert child.readline(2).rstrip() == b'gamma'
        assert child.readline().rstrip() == b'delta'
        child.expect(pexpect.EOF)
        assert not child.isalive()
        assert child.exitstatus == 0

    def test_iter(self):
        " iterating over lines of spawn.__iter__(). "
        child = pexpect.spawn('cat', echo=False)
        child.sendline("abc")
        child.sendline("123")
        child.sendeof()
        # Don't use ''.join() because we want to test __iter__().
        page = b''
        for line in child:
            page += line
        page = page.replace(_CAT_EOF, b'')
        assert page == b'abc\r\n123\r\n'

    def test_readlines(self):
        " reading all lines of spawn.readlines(). "
        child = pexpect.spawn('cat', echo=False)
        child.sendline("abc")
        child.sendline("123")
        child.sendeof()
        page = b''.join(child.readlines()).replace(_CAT_EOF, b'')
        assert page == b'abc\r\n123\r\n'
        child.expect(pexpect.EOF)
        assert not child.isalive()
        assert child.exitstatus == 0

    def test_write(self):
        " write a character and return it in return. "
        child = pexpect.spawn('cat', echo=False)
        child.write('a')
        child.write('\r')
        self.assertEqual(child.readline(), b'a\r\n')

    def test_writelines(self):
        " spawn.writelines() "
        child = pexpect.spawn('cat')
        # notice that much like file.writelines, we do not delimit by newline
        # -- it is equivalent to calling write(''.join([args,]))
        child.writelines(['abc', '123', 'xyz', '\r'])
        child.sendeof()
        line = child.readline()
        assert line == b'abc123xyz\r\n'

    def test_eof(self):
        " call to expect() after EOF is received raises pexpect.EOF "
        child = pexpect.spawn('cat')
        child.sendeof()
        with self.assertRaises(pexpect.EOF):
            child.expect('the unexpected')

    def test_terminate(self):
        " test force terminate always succeeds (SIGKILL). "
        child = pexpect.spawn('cat')
        child.terminate(force=1)
        assert child.terminated

    def test_sighup(self):
        " validate argument `ignore_sighup=True` and `ignore_sighup=False`. "
        # If a parent process sets an Ignore handler for SIGHUP (as on Fedora's
        # build machines), this test breaks. We temporarily restore the default
        # handler, so the child process will quit. However, we can't simply
        # replace any installed handler, because getsignal returns None for
        # handlers not set in Python code, so we wouldn't be able to restore
        # them.
        if signal.getsignal(signal.SIGHUP) == signal.SIG_IGN:
            signal.signal(signal.SIGHUP, signal.SIG_DFL)
            restore_sig_ign = True
        else:
            restore_sig_ign = False

        getch = sys.executable + ' getch.py'
        try:
            child = pexpect.spawn(getch, ignore_sighup=True)
            child.expect('READY')
            child.kill(signal.SIGHUP)
            for _ in range(10):
                if not child.isalive():
                    self.fail('Child process should not have exited.')
                time.sleep(0.1)

            child = pexpect.spawn(getch, ignore_sighup=False)
            child.expect('READY')
            child.kill(signal.SIGHUP)
            for _ in range(10):
                if not child.isalive():
                    break
                time.sleep(0.1)
            else:
                self.fail('Child process should have exited.')

        finally:
            if restore_sig_ign:
                signal.signal(signal.SIGHUP, signal.SIG_IGN)

    def test_bad_child_pid(self):
        " assert bad condition error in isalive(). "
        expect_errmsg = re.escape("isalive() encountered condition where ")
        child = pexpect.spawn('cat')
        child.terminate(force=1)
        # Force an invalid state to test isalive
        child.terminated = 0
        try:
            with self.assertRaisesRegexp(pexpect.ExceptionPexpect,
                                         ".*" + expect_errmsg):
                child.isalive()
        finally:
            # Force valid state for child for __del__
            child.terminated = 1

    def test_bad_arguments_suggest_fdpsawn(self):
        " assert custom exception for spawn(int). "
        expect_errmsg = "maybe you want to use fdpexpect.fdspawn"
        with self.assertRaisesRegexp(pexpect.ExceptionPexpect,
                                     ".*" + expect_errmsg):
            pexpect.spawn(1)

    def test_bad_arguments_second_arg_is_list(self):
        " Second argument to spawn, if used, must be only a list."
        with self.assertRaises(TypeError):
            pexpect.spawn('ls', '-la')

        with self.assertRaises(TypeError):
            # not even a tuple,
            pexpect.spawn('ls', ('-la',))

    def test_read_after_close_raises_value_error(self):
        " Calling read_nonblocking after close raises ValueError. "
        # as read_nonblocking underlies all other calls to read,
        # ValueError should be thrown for all forms of read.
        with self.assertRaises(ValueError):
            p = pexpect.spawn('cat')
            p.close()
            p.read_nonblocking()

        with self.assertRaises(ValueError):
            p = pexpect.spawn('cat')
            p.close()
            p.read()

        with self.assertRaises(ValueError):
            p = pexpect.spawn('cat')
            p.close()
            p.readline()

        with self.assertRaises(ValueError):
            p = pexpect.spawn('cat')
            p.close()
            p.readlines()

    def test_isalive(self):
        " check isalive() before and after EOF. (True, False) "
        child = pexpect.spawn('cat')
        assert child.isalive() is True
        child.sendeof()
        child.expect(pexpect.EOF)
        assert child.isalive() is False

    def test_bad_type_in_expect(self):
        " expect() does not accept dictionary arguments. "
        child = pexpect.spawn('cat')
        with self.assertRaises(TypeError):
            child.expect({})

    def test_env(self):
        " check keyword argument `env=' of pexpect.run() "
        default_env_output = pexpect.run('env')
        custom_env_output = pexpect.run('env', env={'_key': '_value'})
        assert custom_env_output != default_env_output
        assert b'_key=_value' in custom_env_output

    def test_cwd(self):
        " check keyword argument `cwd=' of pexpect.run() "
        tmp_dir = os.path.realpath(tempfile.gettempdir())
        default = pexpect.run('pwd')
        pwd_tmp = pexpect.run('pwd', cwd=tmp_dir).rstrip()
        assert default != pwd_tmp
        assert tmp_dir == _u(pwd_tmp)

    def _test_searcher_as(self, searcher, plus=None):
        # given,
        given_words = ['alpha', 'beta', 'gamma', 'delta', ]
        given_search = given_words
        if searcher == pexpect.searcher_re:
            given_search = [re.compile(word) for word in given_words]
        if plus is not None:
            given_search = given_search + [plus]
        search_string = searcher(given_search)
        basic_fmt = '\n    {0}: {1}'
        fmt = basic_fmt
        if searcher is pexpect.searcher_re:
            fmt = '\n    {0}: re.compile({1})'
        expected_output = '{0}:'.format(searcher.__name__)
        idx = 0
        for word in given_words:
            expected_output += fmt.format(idx, '"{0}"'.format(word))
            idx += 1
        if plus is not None:
            if plus == pexpect.EOF:
                expected_output += basic_fmt.format(idx, 'EOF')
            elif plus == pexpect.TIMEOUT:
                expected_output += basic_fmt.format(idx, 'TIMEOUT')

        # exercise,
        assert search_string.__str__() == expected_output

    def test_searcher_as_string(self):
        " check searcher_string(..).__str__() "
        self._test_searcher_as(pexpect.searcher_string)

    def test_searcher_as_string_with_EOF(self):
        " check searcher_string(..).__str__() that includes EOF "
        self._test_searcher_as(pexpect.searcher_string, plus=pexpect.EOF)

    def test_searcher_as_string_with_TIMEOUT(self):
        " check searcher_string(..).__str__() that includes TIMEOUT "
        self._test_searcher_as(pexpect.searcher_string, plus=pexpect.TIMEOUT)

    def test_searcher_re_as_string(self):
        " check searcher_re(..).__str__() "
        self._test_searcher_as(pexpect.searcher_re)

    def test_searcher_re_as_string_with_EOF(self):
        " check searcher_re(..).__str__() that includes EOF "
        self._test_searcher_as(pexpect.searcher_re, plus=pexpect.EOF)

    def test_searcher_re_as_string_with_TIMEOUT(self):
        " check searcher_re(..).__str__() that includes TIMEOUT "
        self._test_searcher_as(pexpect.searcher_re, plus=pexpect.TIMEOUT)

    def test_nonnative_pty_fork(self):
        " test forced self.__fork_pty() and __pty_make_controlling_tty "
        # given,
        class spawn_ourptyfork(pexpect.spawn):
            def _spawn(self, command, args=[]):
                self.use_native_pty_fork = False
                pexpect.spawn._spawn(self, command, args)

        # exercise,
        p = spawn_ourptyfork('cat', echo=False)
        # verify,
        p.sendline('abc')
        p.expect('abc')
        p.sendeof()
        p.expect(pexpect.EOF)
        assert not p.isalive()

    def test_exception_tb(self):
        " test get_trace() filters away pexpect/__init__.py calls. "
        p = pexpect.spawn('sleep 1')
        try:
            p.expect('BLAH')
        except pexpect.ExceptionPexpect as e:
            # get_trace should filter out frames in pexpect's own code
            tb = e.get_trace()
            # exercise,
            assert 'raise ' not in tb
            assert 'pexpect/__init__.py' not in tb
        else:
            assert False, "Should have raised an exception."

class TestCaseCanon(PexpectTestCase.PexpectTestCase):
    " Test expected Canonical mode behavior (limited input line length)."
    #
    # All systems use the value of MAX_CANON which can be found using
    # fpathconf(3) value PC_MAX_CANON -- with the exception of Linux.
    #
    # Linux, though defining a value of 255, actually honors the value
    # of 4096 from linux kernel include file tty.h definition N_TTY_BUF_SIZE.
    #
    # Linux also does not honor IMAXBEL. termios(3) states, "Linux does not
    # implement this bit, and acts as if it is always set." Although these
    # tests ensure it is enabled, this is a non-op for Linux.
    #
    # These tests only ensure the correctness of the behavior described by
    # the sendline() docstring. pexpect is not particularly involved in these
    # scenarios, though if we wish to expose some kind of interface to
    # tty.setraw, for example, these tests may be re-purposed as such.

    def setUp(self):
        super(TestCaseCanon, self).setUp()
        
        # all systems use PC_MAX_CANON ..
        self.max_input = os.fpathconf(1, 'PC_MAX_CANON')

        # except for linux, which uses 4096,
        if sys.platform.lower().startswith('linux'):
           self.max_input = 4096

    def test_under_max_canon(self):
        " BEL is not sent by terminal driver at maximum bytes - 1. "
        # given,
        child = pexpect.spawn('bash', echo=True, timeout=5)
        child.sendline('stty icanon imaxbel')
        child.sendline('cat')
        send_bytes = self.max_input - 1

        # exercise,
        child.send('_' * send_bytes)
        child.sendline()

        # verify, all input is received
        child.expect_exact('_' * send_bytes)

        # BEL is not found,
        with self.assertRaises(pexpect.TIMEOUT):
            child.expect_exact('\a')

        # cleanup,
        child.sendeof()   # exit cat(1)
        child.sendeof()   # exit bash(1)
        child.expect(pexpect.EOF)
        assert not child.isalive()
        assert child.exitstatus == 0

    def test_at_max_icanon(self):
        " a single BEL is sent when maximum bytes (exactly) is reached. "
        # given,
        child = pexpect.spawn('bash', echo=True, timeout=5)
        child.sendline('stty icanon imaxbel')
        child.sendline('cat')
        send_bytes = self.max_input

        # exercise,
        child.send('_' * send_bytes)
        child.sendline()  # also rings bel; not received

        # we must now backspace to send carriage return
        child.sendcontrol('h')
        child.sendline()

        # verify, all input is *not* received
        with self.assertRaises(pexpect.TIMEOUT):
            child.expect_exact('_' * send_bytes)

        # however, the length of (maximum - 1) is.
        child.expect_exact('_' * (send_bytes - 1))

        # and BEL is found immediately after,
        child.expect_exact('\a')

        # and again, verify only (maximum - 1) is received by cat(1).
        child.expect_exact('_' * (send_bytes - 1))

        # cleanup,
        child.sendeof()         # exit cat(1)
        child.sendeof()         # exit bash(1)
        child.expect(pexpect.EOF)
        assert not child.isalive()
        assert child.exitstatus == 0


    def test_max_no_icanon(self):
        " may be exceed maximum input bytes if canonical mode is disabled. "
        # given,
        child = pexpect.spawn('bash', echo=True, timeout=5)
        child.sendline('stty -icanon imaxbel')
        child.sendline('cat')
        send_bytes = self.max_input + 11

        # exercise,
        child.send('_' * send_bytes)
        child.sendline()

        # verify, all input is received on output (echo)
        child.expect_exact('_' * send_bytes)

        # BEL is *not* found,
        with self.assertRaises(pexpect.TIMEOUT):
            child.expect_exact('\a')

        # verify cat(1) also received all input,
        child.expect_exact('_' * send_bytes)
 
        # cleanup,
        child.sendcontrol('c')  # exit cat(1)
        child.sendline('true')  # ensure exit status of 0 for,
        child.sendline('exit')  # exit bash(1)
        child.expect(pexpect.EOF)
        assert not child.isalive()
        assert child.exitstatus == 0


if __name__ == '__main__':
    unittest.main()

suite = unittest.makeSuite(TestCaseMisc,'test')

