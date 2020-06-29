"""SCons.Platform.posix

Platform-specific initialization for POSIX (Linux, UNIX, etc.) systems.

There normally shouldn't be any need to import this module directly.  It
will usually be imported through the generic SCons.Platform.Platform()
selection method.
"""

#
# __COPYRIGHT__
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

__revision__ = "__FILE__ __REVISION__ __DATE__ __DEVELOPER__"

import errno
import os
import os.path
import subprocess
import sys
import select

import SCons.Util
from SCons.Platform import TempFileMunge, stubprocess_wrapper
from SCons.Platform.virtualenv import ImportVirtualenv
from SCons.Platform.virtualenv import ignore_virtualenv, enable_virtualenv

if stubprocess_wrapper:
    # Create a copy of the subprocess.Popen by subclassing
    class PopenWrapped(subprocess.Popen):
        pass
    
    # We sneak our new 'wrapped' Popen into the subprocess module,
    # such that the original subprocess.Popen() is guaranteed to stay
    # unchanged. Otherwise, wrapping the Popen() directly might interfere
    # with user SConstructs where subprocess is imported directly.
    # Here we try to ensure that only SCons' spawn calls are redirected
    # through the PopenWrapped().
    subprocess.PopenWrapped = PopenWrapped
    
    # Now try to import and activate Parts' stubprocess wrapper for
    # speeding up process forks...if this isn't possible for some reason,
    # our subprocess.PopenWrapped() will still behave exactly the same as the
    # builtin subprocess.Popen().
    import SCons.Platform.stubprocess
else:
    subprocess.PopenWrapped = subprocess.Popen

exitvalmap = {
    2 : 127,
    13 : 126,
}

def escape(arg):
    """escape shell special characters"""
    slash = '\\'
    special = '"$'

    arg = arg.replace(slash, slash+slash)
    for c in special:
        arg = arg.replace(c, slash+c)

    # print("ESCAPE RESULT: %s" % arg)
    return '"' + arg + '"'


def exec_subprocess(l, env):
    proc = subprocess.PopenWrapped(l, env = env, close_fds = True)
    return proc.wait()

def subprocess_spawn(sh, escape, cmd, args, env):
    return exec_subprocess([sh, '-c', ' '.join(args)], env)

def exec_popen3(l, env, stdout, stderr):
    proc = subprocess.PopenWrapped(l, env = env, close_fds = True,
                            stdout = stdout,
                            stderr = stderr)
    return proc.wait()

def piped_env_spawn(sh, escape, cmd, args, env, stdout, stderr):
    # spawn using Popen3 combined with the env command
    # the command name and the command's stdout is written to stdout
    # the command's stderr is written to stderr
    return exec_popen3([sh, '-c', ' '.join(args)],
                       env, stdout, stderr)


def generate(env):
    # Bearing in mind we have python 2.4 as a baseline, we can just do this:
    spawn = subprocess_spawn
    pspawn = piped_env_spawn
    # Note that this means that 'escape' is no longer used

    if 'ENV' not in env:
        env['ENV']        = {}
    env['ENV']['PATH']    = '/usr/local/bin:/opt/bin:/bin:/usr/bin'
    env['OBJPREFIX']      = ''
    env['OBJSUFFIX']      = '.o'
    env['SHOBJPREFIX']    = '$OBJPREFIX'
    env['SHOBJSUFFIX']    = '$OBJSUFFIX'
    env['PROGPREFIX']     = ''
    env['PROGSUFFIX']     = ''
    env['LIBPREFIX']      = 'lib'
    env['LIBSUFFIX']      = '.a'
    env['SHLIBPREFIX']    = '$LIBPREFIX'
    env['SHLIBSUFFIX']    = '.so'
    env['LIBPREFIXES']    = [ '$LIBPREFIX' ]
    env['LIBSUFFIXES']    = [ '$LIBSUFFIX', '$SHLIBSUFFIX' ]
    env['PSPAWN']         = pspawn
    env['SPAWN']          = spawn
    env['SHELL']          = 'sh'
    env['ESCAPE']         = escape
    env['TEMPFILE']       = TempFileMunge
    env['TEMPFILEPREFIX'] = '@'
    #Based on LINUX: ARG_MAX=ARG_MAX=131072 - 3000 for environment expansion
    #Note: specific platforms might rise or lower this value
    env['MAXLINELENGTH']  = 128072

    # This platform supports RPATH specifications.
    env['__RPATH'] = '$_RPATH'

    # GDC is GCC family, but DMD and LDC have different options.
    # Must be able to have GCC and DMD work in the same build, so:
    env['__DRPATH'] = '$_DRPATH'

    if enable_virtualenv and not ignore_virtualenv:
        ImportVirtualenv(env)

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
