# MIT License
#
# Copyright The SCons Foundation
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

import collections
import os
import unittest

import TestCmd

import SCons.Scanner.D

test = TestCmd.TestCmd(workdir = '')


class DummyEnvironment(collections.UserDict):
    def __init__(self, **kwargs):
        super().__init__()
        self.data.update(kwargs)
        self.fs = SCons.Node.FS.FS(test.workpath(''))

    def Dictionary(self, *args):
        return self.data

    def subst(self, strSubst, target=None, source=None, conv=None):
        if strSubst[0] == '$':
            return self.data[strSubst[1:]]
        return strSubst

    def subst_list(self, strSubst, target=None, source=None, conv=None):
        if strSubst[0] == '$':
            return [self.data[strSubst[1:]]]
        return [[strSubst]]

    def subst_path(self, path, target=None, source=None, conv=None):
        if not isinstance(path, list):
            path = [path]
        return list(map(self.subst, path))

    def get_calculator(self):
        return None

    def get_factory(self, factory):
        return factory or self.fs.File

    def Dir(self, filename):
        return self.fs.Dir(filename)

    def File(self, filename):
        return self.fs.File(filename)

if os.path.normcase('foo') == os.path.normcase('FOO'):
    my_normpath = os.path.normcase
else:
    my_normpath = os.path.normpath

def deps_match(self, deps, headers):
    global my_normpath
    scanned = list(map(my_normpath, list(map(str, deps))))
    expect = list(map(my_normpath, headers))
    self.assertTrue(scanned == expect, "expect %s != scanned %s" % (expect, scanned))

"""
Examples from https://dlang.org/spec/module.html

D Language: 2.071.1
Accessed: 11 August 2016
"""

# Regular import
test.write('basic.d',"""
import A;

void main() {}
""")

# Static import
test.write('static.d',"""
static import A;

void main()
{
    std.stdio.writeln("hello!"); // ok, writeln is fully qualified
}
""")

# Public import
test.write('public.d',"""
public import A;

void main() {}
""")

# Renamed import
test.write('rename.d',"""
import B = A;

void main()
{
    io.writeln("hello!");        // ok, calls std.stdio.writeln
}
""")

# Selective import
test.write('selective.d',"""
import A : B, C;

void main()
{
    writeln("hello!");           // ok, writeln bound into current namespace
    foo("world");                // ok, calls std.stdio.write()
}
""")

# Renamed and Selective import
test.write('renameAndSelective.d',"""
import B = A : C = D;

void main()
{
}
""")

# Scoped import
test.write('scoped.d',"""
void main()
{
    import A;
}
""")

# Combinatorial import
test.write('combinatorial.d',"""
import A, B, CCC = C, DDD = D : EEE = FFF;

void main()
{
}
""")

# Subdirs import
test.write('subdirs.d',"""
import X.Y, X.Z, X.X.X;

void main() {}
""")

# Multiple import
test.write('multiple.d',"""
public import B;
static import C;

import X = X.Y : Q, R, S, T = U;
void main()
{
    import A;
}
""")

# Multiline import
test.write('multiline.d',"""
import
A;

void main() {}
""")

test.write('A.d',"""
module A;
void main() {}
""")

test.write('B.d',"""
module B;
void main() {}
""")

test.write('C.d',"""
module C;
void main() {}
""")

test.write('D.d',"""
module D;
void main() {}
""")

test.subdir('X', os.path.join('X','X'))

test.write(os.path.join('X','Y.d'),"""
module Y;
void main() {}
""")

test.write(os.path.join('X','Z.d'),"""
module Z;
void main() {}
""")

test.write(os.path.join('X','X','X.d'),"""
module X;
void main() {}
""")

class DScannerTestCase(unittest.TestCase):
    def helper(self, filename, headers):
        env = DummyEnvironment()
        s = SCons.Scanner.D.DScanner()
        path = s.path(env)
        deps = s(env.File(filename), env, path)
        deps_match(self, deps, headers)

    def test_BasicImport(self):
        self.helper('basic.d', ['A.d'])

    def test_StaticImport(self):
        self.helper('static.d', ['A.d'])

    def test_publicImport(self):
        self.helper('public.d', ['A.d'])
    
    def test_RenameImport(self):
        self.helper('rename.d', ['A.d'])

    def test_SelectiveImport(self):
        self.helper('selective.d', ['A.d'])

    def test_RenameAndSelectiveImport(self):
        self.helper('renameAndSelective.d', ['A.d'])

    def test_ScopedImport(self):
        self.helper('scoped.d', ['A.d'])

    def test_CombinatorialImport(self):
        self.helper('combinatorial.d', ['A.d', 'B.d', 'C.d', 'D.d'])

    def test_SubdirsImport(self):
        self.helper('subdirs.d', [os.path.join('X','X','X.d'), os.path.join('X','Y.d'), os.path.join('X','Z.d')])

    def test_MultipleImport(self):
        self.helper('multiple.d', ['A.d', 'B.d', 'C.d', os.path.join('X','Y.d')])

    def test_MultilineImport(self):
        self.helper('multiline.d', ['A.d'])

if __name__ == "__main__":
    unittest.main()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
