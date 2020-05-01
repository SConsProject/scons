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

import TestSCons

test = TestSCons.TestSCons()

test.write('SConstruct', r"""
env = Environment()
env.Command('test.out', 'test.in', Copy('$TARGET', '$SOURCE'))
env.InstallAs('test2.out', 'test.out')
# Mark test2.out as precious so we'll handle the exception in
# FunctionAction() rather than when the target is cleaned before building.
env.Precious('test2.out')
env.Default('test2.out')
""")

test.write('test.in', "test.in 1\n")

test.run(arguments = '.')

test.write('test.in', "test.in 2\n")

test.writable('test2.out', 0)
f = open(test.workpath('test2.out'))

test.run(arguments = '.',
         stderr = None,
         status = 2)

f.close()
test.writable('test2.out', 1)

test.description_set("Incorrect STDERR:\n%s" % test.stderr())
stderr_lines = test.stderr().splitlines()
test.description_set("Incorrect STDERR:\n%s" % stderr_lines)

#TODO need windows specific first line..
errs = [
    "cp: cannot create regular file 'test2.out': Permission denied",
    "scons: *** [test2.out] Error 1",
]
test.fail_test(stderr_lines != errs)

test.pass_test()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
