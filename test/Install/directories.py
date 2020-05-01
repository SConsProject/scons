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
Test using Install() on directories.
"""

import os.path

import TestSCons

test = TestSCons.TestSCons()

test.subdir('outside',
            'work',
            ['work', 'dir1'],
            ['work', 'dir1', 'sub'],
            ['work', 'dir2'],
            ['work', 'dir2', 'sub'],
            ['work', 'dir3'],
            ['work', 'dir3', 'sub'],
            ['work', 'dir4'],
            ['work', 'dir4', 'sub'])

test.write(['work', 'SConstruct'], """\
DefaultEnvironment(tools=[])
env = Environment(tools=[]) 

Install('../outside',  'dir1')
InstallAs('../outside/d2', 'dir2')

env.Install('../outside',  'dir3')
env.InstallAs('../outside/d4',  'dir4')
""")

test.write(['work', 'f1'], "work/f1\n")
test.write(['work', 'dir1', 'f2'], "work/dir1/f2\n")
test.write(['work', 'dir1', 'sub', 'f3'], "work/dir1/sub/f3\n")
test.write(['work', 'dir2', 'f4'], "work/dir2/f4\n")
test.write(['work', 'dir2', 'sub', 'f5'], "work/dir2/sub/f5\n")
test.write(['work', 'dir3', 'f6'], "work/dir3/f6\n")
test.write(['work', 'dir3', 'sub', 'f7'], "work/dir3/sub/f7\n")
test.write(['work', 'dir4', 'f8'], "work/dir4/f8\n")
test.write(['work', 'dir4', 'sub', 'f9'], "work/dir4/sub/f9\n")

arguments = [
    test.workpath('outside', 'd2'),
    test.workpath('outside', 'd4'),
    test.workpath('outside', 'dir1'),
    test.workpath('outside', 'dir3'),
]

expect = test.wrap_stdout("""\
Install directory: "dir2" as "%s"
Install directory: "dir4" as "%s"
Install directory: "dir1" as "%s"
Install directory: "dir3" as "%s"
""" % tuple(arguments))



test.run(chdir='work', arguments=arguments, stdout=expect)

test.must_match(test.workpath('outside', 'dir1', 'f2'), "work/dir1/f2\n")
test.must_match(test.workpath('outside', 'dir1', 'sub', 'f3'), "work/dir1/sub/f3\n")
test.must_match(test.workpath('outside', 'd2', 'f4'), "work/dir2/f4\n")
test.must_match(test.workpath('outside', 'd2', 'sub', 'f5'), "work/dir2/sub/f5\n")
test.must_match(test.workpath('outside', 'dir3', 'f6'), "work/dir3/f6\n")
test.must_match(test.workpath('outside', 'dir3', 'sub', 'f7'), "work/dir3/sub/f7\n")
test.must_match(test.workpath('outside', 'd4', 'f8'), "work/dir4/f8\n")
test.must_match(test.workpath('outside', 'd4', 'sub', 'f9'), "work/dir4/sub/f9\n")

test.pass_test()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
