# This is the "stubprocess.py" wrapper.
# It is used within the SCons project by kind permission of the Parts team, including the
# permission by INTEL to make this code publicly available.
# Our thanks for this valuable contribution go to the authors of the wrapper
#
#    Eugene Leskinen, Vasilij Litvinov and Jason Kenny.
#
# This version of the wrapper was taken from the Parts repo at 
# https://bitbucket.org/sconsparts/parts.git, in version v0.15.4,
# commit 4f2a0e97e24b410d098df57ddc4247ebfb2aa636.
# It has been adapted to Python3 and got slightly modified,
# such that it doesn't wrap the builtin subprocess.Popen()
# anymore. Instead, the SCons code in posix.py creates a copy subprocess.PopenWrapped()
# which then gets modified and wrapped below.
# This is done to protect us from any side-effects with users' SConstructs, or the
# way they are importing SCons and other packages to their scripts.
#
#
# Copyright (c) 2008-2018 Jason Kenny and contributors
#
# All rights reserved.
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

'''
We have faced an issue with forking processes on RHEL 5.10.
When parent process consumes a realy big amount of memory fork call becomes very slow
because it needs to copy memory pages from parent to child process.
To overcome the issue we use posix_spawn function. The function calls vfork followed by
execve call. This avoids copying of memory pages and saves time but it also prevents us
from redirecting standard input and output because when it is requested posix_spawn
function uses fork instead of vfork and we have the slowdown again.

To make the IO redirection we do not start a requested sub-process immidiately but
use intermediate python script which redirects the IO. The whole call chain looks like this:

Popen("/foo/bar") -> fork -> execve(["python", __file__]) -> execve("/foo/bar")

All parameters needed for I/O redirection are passed in pickle via temporary file.
'''


import sys
from builtins import range

if sys.platform in ('linux', 'darwin'):
     
    import os
    import pickle
    import fcntl
    import traceback
    import base64

    try:
        cloexec_flag = fcntl.FD_CLOEXEC
    except AttributeError:
        cloexec_flag = 1

    def _set_cloexec_flag(fd, cloexec=True):
        '''
        Utility function to modify close-on-exec flag of specified file descriptor
        '''
        old = fcntl.fcntl(fd, fcntl.F_GETFD)
        if cloexec:
            fcntl.fcntl(fd, fcntl.F_SETFD, old | cloexec_flag)
        else:
            fcntl.fcntl(fd, fcntl.F_SETFD, old & ~cloexec_flag)

    if __name__ == '__main__':
        try:
            MAXFD = os.sysconf("SC_OPEN_MAX")
        except Exception:
            MAXFD = 256

        try:
            from os import closerange
        except ImportError:
            def _close_fds(but):
                '''
                Closes all open file descriptors
                '''
                for i in range(3, MAXFD):
                    try:
                        if i != but:
                            os.close(i)
                    except Exception:
                        pass
        else:
            def _close_fds(but):
                closerange(3, but)
                closerange(but + 1, MAXFD)

        def report_exception(errpipe_write):
            exc_type, exc_value, tb = sys.exc_info()
            del exc_type, tb
            # Save the traceback and attach it to the exception object
            exc_lines = traceback.format_exc()
            exc_value.child_traceback = ''.join(exc_lines)
            os.write(errpipe_write, pickle.dumps(exc_value))

        def do_execv(args=None, executable=None, close_fds=None, cwd=None, env=None, restore_signals=None,
                     shell=None, p2cread=None, p2cwrite=None, c2pread=None, c2pwrite=None,
                     errread=None, errwrite=None, errpipe_read=None, errpipe_write=None):
            '''
            The function redirects IO, prepares command-line, sets up environment and
            executes execve function.
            '''
            if errpipe_read:
                errpipe_read = int(errpipe_read)
            if errpipe_write:
                errpipe_write = int(errpipe_write)

            os.close(errpipe_read)
            _set_cloexec_flag(errpipe_write, True)
            try:

                if shell:
                    args = [executable or "/bin/sh", "-c"] + args

                if executable is None:
                    executable = args[0]

                # Close parent's pipe ends
                for parent_end, child_end in ((p2cwrite, p2cread), (c2pread, c2pwrite),
                                              (errread, errwrite)):
                    if parent_end is not None and parent_end != -1:
                        os.close(parent_end)
                    if child_end is not None and child_end != -1:
                        _set_cloexec_flag(child_end, True)

                # When duping fds, if there arises a situation
                # where one of the fds is either 0, 1 or 2, it
                # is possible that it is overwritten (#12607).
                if c2pwrite == 0:
                    c2pwrite = os.dup(c2pwrite)
                if errwrite == 0 or errwrite == 1:
                    errwrite = os.dup(errwrite)

                # Dup fds for child
                def _dup2(a, b):
                    # dup2() removes the CLOEXEC flag but
                    # we must do it ourselves if dup2()
                    # would be a no-op (issue #10806).
                    if a == b:
                        _set_cloexec_flag(a, False)
                    elif a is not None and a != -1:
                        os.dup2(a, b)
                _dup2(p2cread, 0)
                _dup2(c2pwrite, 1)
                _dup2(errwrite, 2)

                # Close pipe fds.  Make sure we don't close the
                # same fd more than once, or standard fds.
                closed = set([None])
                for fd in [p2cread, c2pwrite, errwrite]:
                    if fd not in closed and fd > 2:
                        os.close(fd)
                        closed.add(fd)

                # Close all other fds, if asked for
                if close_fds:
                    _close_fds(errpipe_write)

                if cwd is not None:
                    os.chdir(cwd)

                if env is None:
                    os.execvp(executable, args)
                else:
                    os.execvpe(executable, args, env)
            except Exception:
                report_exception(errpipe_write)

            # This exitcode won't be reported to applications, so it
            # really doesn't matter what we return.
            os._exit(255)

        errpipe_write = int(sys.argv[1])
        try:
            if sys.argv[2] == '@':
                with open(sys.argv[3], 'rb') as data:
                    data = data.read()
                os.unlink(sys.argv[3])
            else:
                data = sys.argv[2].encode('utf-8')
            params = pickle.loads(base64.decodebytes(data))
            do_execv(**params)
        except Exception:
            report_exception(errpipe_write)

    else:
        import ctypes
        import tempfile

        try:
            ARG_MAX = os.sysconf('SC_ARG_MAX')
        except Exception:
            ARG_MAX = 32768

        # Removed eintr_retry_call see:
        # Issue #23285: PEP 475 -- Retry system calls failing with EINTR.
        
        try:
            # We support only Linux and Mac OS X now.
            libc = ctypes.CDLL("libc.so.6" if 'linux' in sys.platform else 'libc.dylib', use_errno=True)
            posix_spawn = libc.posix_spawn
        except (OSError, AttributeError):
            # OSError is raised when no libc.so.6 is found on the system
            # AttributeError is raised when no posix_spawn function can be found
            pass
        else:
            posix_spawn.restype = ctypes.c_int
            posix_spawn.argtypes = (
                ctypes.POINTER(ctypes.c_int),  # ppid
                ctypes.c_char_p,  # executable
                ctypes.c_void_p,  # file_actions
                ctypes.c_void_p,  # attrp
                ctypes.POINTER(ctypes.c_char_p),  # argv
                ctypes.POINTER(ctypes.c_char_p),  # env
            )

            # Caching a few encoded strings that we'll need below
            sys_executable_encoded = sys.executable.encode('utf-8')
            file_encoded = __file__.encode('utf-8')
            atsign_encoded = '@'.encode('utf-8')


            # In Python subprocess.Popen._execute_child accepts different numbers of arguments.
            # To workaround the issue we use _unpack_args* functions. The tuple containing
            # the args is then passed to the _execute_child
            # function.

            def _unpack_args_3(args):
                """ Args in Python 3.0-3.1 were:
                    (self, argv, executable, preexec_fn, close_fds,
                     cwd, env, universal_newlines,
                     startupinfo, creationflags, shell,
                     p2cread, p2cwrite,
                     c2pread, c2pwrite,
                     errread, errwrite)
                """
                result = (self, argv, executable, preexec_fn, close_fds, pass_fds,
                          cwd, env, universal_newlines,
                          startupinfo, creationflags, shell,
                          p2cread, p2cwrite,
                          c2pread, c2pwrite,
                          errread, errwrite, restore_signals, start_new_session) = args[:5] + (None,) + args[5:] + (True, False)
                return result

            def _unpack_args_32(args):
                """ Args in Python 3.2-3.6.8 were:
                    (self, argv, executable, preexec_fn, close_fds,
                     cwd, env,
                     startupinfo, creationflags, shell,
                     p2cread, p2cwrite,
                     c2pread, c2pwrite,
                     errread, errwrite)
                """
                result = (self, argv, executable, preexec_fn, close_fds, pass_fds,
                          cwd, env, universal_newlines,
                          startupinfo, creationflags, shell,
                          p2cread, p2cwrite,
                          c2pread, c2pwrite,
                          errread, errwrite, restore_signals, start_new_session) = args[:5] + (None,) + args[5:6] + (None,) + args[6:] + (True, False)
                return result

            def _unpack_args_369(args):
                """ Args from Python 3.6.9 on were:
                    (self, argv, executable, preexec_fn, close_fds, pass_fds
                     cwd, env,
                     startupinfo, creationflags, shell,
                     p2cread, p2cwrite,
                     c2pread, c2pwrite,
                     errread, errwrite, restore_signals, start_new_session)
                """
                result = (self, argv, executable, preexec_fn, close_fds, pass_fds,
                          cwd, env, universal_newlines,
                          startupinfo, creationflags, shell,
                          p2cread, p2cwrite,
                          c2pread, c2pwrite,
                          errread, errwrite, restore_signals, start_new_session) = args[:8] + (None,) + args[8:]
                return result

            if sys.version_info >= (3, 6, 9):
                _unpack_args = _unpack_args_369
            else:
                if sys.version_info >= (3, 2):
                    _unpack_args = _unpack_args_32
                else:
                    _unpack_args = _unpack_args_3

            def _close_in_parent(fd, to_close):
                if fd != -1:
                    os.close(fd)
                    to_close.remove(fd)

            def _wrap_execute_child(klass):
                wrapped_execute_child = klass._execute_child

                def _execute_child(*argv):

                    (self, args, executable, preexec_fn, close_fds, pass_fds,
                     cwd, env, universal_newlines,
                     startupinfo, creationflags, shell,
                     p2cread, p2cwrite,
                     c2pread, c2pwrite,
                     errread, errwrite, restore_signals, start_new_session) = _unpack_args(argv)

                    to_close = set((p2cread, p2cwrite, c2pread, c2pwrite, errread, errwrite))
            
                    if preexec_fn:
                        return wrapped_execute_child(*argv)

                    for fd in (p2cread, p2cwrite,
                               c2pread, c2pwrite,
                               errread, errwrite):
                        if fd is not None and fd > 2:
                            _set_cloexec_flag(fd, False)

                    errpipe_read, errpipe_write = os.pipe()
                    errpipe_read_encoded = str(errpipe_read).encode('utf-8')
                    errpipe_write_encoded = str(errpipe_write).encode('utf-8')
                    # Starting in Python 3.4 file descriptors aren't inheritable
                    # by default anymore...
                    os.set_inheritable(errpipe_read, True)
                    os.set_inheritable(errpipe_write, True)
                    
                    if isinstance(args, (str, bytes)):
                        args = [args]

                    if env:
                        env = dict((str(key), str(value))
                                   for (key, value) in env.items())
                    else:
                        env = None
                    if executable:
                        executable = str(executable)
                    else:
                        executable = None
                    if cwd:
                        cwd = str(cwd)
                    else:
                        cwd = None

                    data = base64.encodestring(
                        pickle.dumps(
                            dict(
                                args=args, executable=executable, close_fds=bool(close_fds),
                                cwd=cwd, env=env, restore_signals=bool(restore_signals), shell=bool(shell),
                                p2cread=p2cread, p2cwrite=p2cwrite,
                                c2pread=c2pread, c2pwrite=c2pwrite,
                                errread=errread, errwrite=errwrite,
                                errpipe_read=errpipe_read_encoded,
                                errpipe_write=errpipe_write_encoded,
                            ), pickle.HIGHEST_PROTOCOL))

                    use_file = len(data) >= ARG_MAX

                    if use_file:
                        with tempfile.NamedTemporaryFile(delete=False) as the_file:
                            the_file.write(data)
                        argv = (sys_executable_encoded,
                                file_encoded,
                                errpipe_write_encoded,
                                atsign_encoded,
                                the_file.name.encode('utf-8'), 0)
                    else:
                        argv = (sys_executable_encoded,
                                file_encoded,
                                errpipe_write_encoded,
                                data, 0)
                    argv = (ctypes.c_char_p * len(argv))(*argv)

                    pid = ctypes.c_int()

                    os_environ = (ctypes.c_char_p * (len(os.environ) + 1))(
                        *(['{0}={1}'.format(*value).encode('utf-8') for value in os.environ.items()] + [0]))

                    try:
                        ret = posix_spawn(ctypes.byref(pid), ctypes.c_char_p(sys_executable_encoded),
                                          ctypes.c_void_p(), ctypes.c_void_p(),
                                          ctypes.cast(argv, ctypes.POINTER(ctypes.c_char_p)),
                                          ctypes.cast(os_environ, ctypes.POINTER(ctypes.c_char_p)))
                        err = ctypes.get_errno()
                        os.close(errpipe_write)
                        if ret:
                            raise OSError(err, os.strerror(err))
                        self.pid = pid.value
                        self._child_created = True
                        
                        # Wait for exec to fail or succeed; possibly raising an
                        # exception (limited in size)
                        errpipe_data = bytearray()
                        while True:
                            part = os.read(errpipe_read, 50000)
                            errpipe_data += part
                            if not part or len(errpipe_data) > 50000:
                                break
                        
                        if errpipe_data:
                            try:
                                pid, sts = os.waitpid(self.pid, 0)
                                if pid == self.pid:
                                    self._handle_exitstatus(sts)
                                else:
                                    self.returncode = sys.maxsize
                            except ChildProcessError:
                                pass
                            raise pickle.loads(data)
                    finally:
                        if use_file:
                            try:
                                os.unlink(the_file.name)
                            except Exception:
                                pass
                        os.close(errpipe_read)
                        if p2cread is not None and p2cwrite is not None:
                            _close_in_parent(p2cread, to_close)
                        if c2pwrite is not None and c2pread is not None:
                            _close_in_parent(c2pwrite, to_close)
                        if errwrite is not None and errread is not None:
                            _close_in_parent(errwrite, to_close)

                klass._execute_child = _execute_child

            import subprocess
            _wrap_execute_child(subprocess.PopenWrapped)

# vim: set et ts=4 sw=4 ai :
