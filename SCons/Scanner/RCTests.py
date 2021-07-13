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

import unittest
import collections
import os

import TestCmd

import SCons.Scanner.RC
import SCons.Node.FS
import SCons.Warnings

test = TestCmd.TestCmd(workdir = '')

os.chdir(test.workpath(''))

# create some source files and headers:

test.write('t1.rc','''
#include "t1.h"
''')

test.write('t2.rc',"""
#include "t1.h"
ICO_TEST               ICON    DISCARDABLE     "abc.ico"
BMP_TEST               BITMAP  DISCARDABLE     "def.bmp"
cursor1 CURSOR "bullseye.cur"
ID_RESPONSE_ERROR_PAGE  HTML  "responseerrorpage.htm"
5 FONT  "cmroman.fnt"
1  MESSAGETABLE "MSG00409.bin"
1  MESSAGETABLE MSG00410.bin
1 TYPELIB "testtypelib.tlb"
TEST_REGIS   REGISTRY MOVEABLE PURE  "testregis.rgs"
TEST_D3DFX   D3DFX DISCARDABLE "testEffect.fx"

""")

test.write('t3.rc','#include "t1.h"\r\n')

# Create dummy include files
headers = ['t1.h',
           'abc.ico','def.bmp','bullseye.cur','responseerrorpage.htm','cmroman.fnt',
           'testEffect.fx',
           'MSG00409.bin','MSG00410.bin','testtypelib.tlb','testregis.rgs']

for h in headers:
    test.write(h, " ")


# define some helpers:

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

    def subst_path(self, path, target=None, source=None, conv=None):
        if not isinstance(path, list):
            path = [path]
        return list(map(self.subst, path))

    def __contains__(self, key):
        return key in self.data

    def get_calculator(self):
        return None

    def get_factory(self, factory):
        return factory or self.fs.File

    def Dir(self, filename):
        return self.fs.Dir(filename)

    def File(self, filename):
        return self.fs.File(filename)

global my_normpath
my_normpath = os.path.normpath

if os.path.normcase('foo') == os.path.normcase('FOO'):
    my_normpath = os.path.normcase

def deps_match(self, deps, headers):
    scanned = sorted(map(my_normpath, list(map(str, deps))))
    expect = sorted(map(my_normpath, headers))
    self.assertTrue(scanned == expect, "expect %s != scanned %s" % (expect, scanned))

# define some tests:

class RCScannerTestCase1(unittest.TestCase):
    def runTest(self):
        path = []
        env = DummyEnvironment(RCSUFFIXES=['.rc','.rc2'],
                               CPPPATH=path)
        s = SCons.Scanner.RC.RCScan()
        deps = s(env.File('t1.rc'), env, path)
        headers = ['t1.h']
        deps_match(self, deps, headers)

class RCScannerTestCase2(unittest.TestCase):
    def runTest(self):
        path = []
        env = DummyEnvironment(RCSUFFIXES=['.rc','.rc2'],
                               CPPPATH=path)
        s = SCons.Scanner.RC.RCScan()
        deps = s(env.File('t2.rc'), env, path)
        headers = ['MSG00410.bin',
                   'abc.ico','bullseye.cur',
                   'cmroman.fnt','def.bmp',
                   'MSG00409.bin',
                   'responseerrorpage.htm',
                   't1.h',
                   'testEffect.fx',
                   'testregis.rgs','testtypelib.tlb']
        deps_match(self, deps, headers)

class RCScannerTestCase3(unittest.TestCase):
    def runTest(self):
        path = []
        env = DummyEnvironment(RCSUFFIXES=['.rc','.rc2'],
                               CPPPATH=path)
        s = SCons.Scanner.RC.RCScan()
        deps = s(env.File('t3.rc'), env, path)
        headers = ['t1.h']
        deps_match(self, deps, headers)
        

if __name__ == "__main__":
    unittest.main()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
