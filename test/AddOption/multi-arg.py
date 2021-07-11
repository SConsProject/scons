#!/usr/bin/env python
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

"""
Verify that when an option is specified with nargs > 1,
SCons consumes those correctly into the args.
"""

import TestSCons

test = TestSCons.TestSCons()

# First, test an option with nargs=2 and no others:
test.write('SConstruct', """\
env = Environment()
AddOption('-x', '--extras',
          nargs=2,
          dest='extras',
          action='store',
          type='string',
          metavar='FILE1 FILE2',
          default=(),
          help='two extra files to install')
print(str(GetOption('extras')))
print(COMMAND_LINE_TARGETS)
""")

# no args
test.run('-Q -q .', stdout="()\n['.']\n")

# one arg, should fail
test.run('-Q -q . --extras A', status=2, stderr="""\
usage: scons [OPTION] [TARGET] ...

SCons Error: --extras option requires 2 arguments
""")
#one arg, short option
test.run('-Q -q . -x A', status=2, stderr="""\
usage: scons [OPTION] [TARGET] ...

SCons Error: -x option requires 2 arguments
""")
# two args
test.run('-Q -q . --extras A B', stdout="('A', 'B')\n['.']\n")
# two args, short option
test.run('-Q -q . -x A B', stdout="('A', 'B')\n['.']\n")
# -- means the rest are not processed as args
test.run('-Q -q . -- --extras A B', status=1, stdout="()\n['.', '--extras', 'A', 'B']\n")

# Now test what has been a bug: another option is
# also defined, this impacts the collection of args for the nargs>1 opt
test.write('SConstruct', """\
env = Environment()
AddOption('-P', '--prefix',
          nargs=1,
          dest='prefix',
          action='store',
          type='string',
          metavar='DIR',
          help='installation prefix')
AddOption('-x', '--extras',
          nargs=2,
          dest='extras',
          action='store',
          type='string',
          metavar='FILE1 FILE2',
          default=(),
          help='two extra files to install')
print(str(GetOption('prefix')))
print(str(GetOption('extras')))
print(COMMAND_LINE_TARGETS)
""")
# no opts
test.run('-Q -q .', stdout="None\n()\n['.']\n")
# first opt long, one arg
test.run('-Q -q . --prefix=/home/foo', stdout="/home/foo\n()\n['.']\n")
test.run('-Q -q . --prefix /home/foo', stdout="/home/foo\n()\n['.']\n")
# first opt short, one arg
test.run('-Q -q . -P/home/foo', stdout="/home/foo\n()\n['.']\n")
test.run('-Q -q . -P /home/foo', stdout="/home/foo\n()\n['.']\n")
# second opt long, two args
test.run('-Q -q . --extras=A B', stdout="None\n('A', 'B')\n['.']\n")
test.run('-Q -q . --extras A B', stdout="None\n('A', 'B')\n['.']\n")
# second opt short, two args
test.run('-Q -q . -xA B', stdout="None\n('A', 'B')\n['.']\n")
test.run('-Q -q . -x A B', stdout="None\n('A', 'B')\n['.']\n")
# both opts long
test.run('-Q -q . --prefix=/home/foo --extras=A B', stdout="/home/foo\n('A', 'B')\n['.']\n")
test.run('-Q -q . --prefix /home/foo --extras A B', stdout="/home/foo\n('A', 'B')\n['.']\n")
# both opts short
test.run('-Q -q . -P/home/foo -xA B', stdout="/home/foo\n('A', 'B')\n['.']\n")
test.run('-Q -q . -P /home/foo -x A B', stdout="/home/foo\n('A', 'B')\n['.']\n")
# don't process
test.run('-Q -q . -- --prefix=/home/foo --extras=A B',status=1, 
    stdout="None\n()\n['.', '--prefix=/home/foo', '--extras=A', 'B']\n")
test.run('-Q -q . -- --prefix /home/foo --extras A B',status=1, 
    stdout="None\n()\n['.', '--prefix', '/home/foo', '--extras', 'A', 'B']\n")

test.pass_test()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4: