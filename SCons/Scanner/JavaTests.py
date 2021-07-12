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

import SCons.Scanner.Java
import SCons.Node.FS
import SCons.Warnings


test = TestCmd.TestCmd(workdir = '')
test.subdir('com')

files = [
    'bootclasspath.jar',
    'classpath.jar',
    'Test.class',
    'com/Test.class'
]

for fname in files:
    test.write(fname, "\n")


class DummyEnvironment(collections.UserDict):
    def __init__(self,**kw):
        collections.UserDict.__init__(self)
        self.data.update(kw)
        self.fs = SCons.Node.FS.FS(test.workpath(''))
        self['ENV'] = {}
        
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

    def has_key(self, key):
        return key in self.Dictionary()

    def get_calculator(self):
        return None

    def get_factory(self, factory):
        return factory or self.fs.File

    def Dir(self, filename):
        return self.fs.Dir(filename)

    def File(self, filename):
        return self.fs.File(filename)
    
    def Glob(self, path):
        return self.fs.Glob(path)


class DummyNode:
    def __init__(self, name):
        self.name = name

    def rexists(self):
        return 1

    def __str__(self):
        return self.name


global my_normpath
my_normpath = os.path.normpath

if os.path.normcase('foo') == os.path.normcase('FOO'):
    my_normpath = os.path.normcase

def deps_match(self, deps, headers):
    scanned = sorted(map(my_normpath, list(map(str, deps))))
    expect = sorted(map(my_normpath, headers))
    self.assertTrue(scanned == expect, "expect %s != scanned %s" % (expect, scanned))


class JavaScannerEmptyClasspath(unittest.TestCase):
    def runTest(self):
        path = []
        env = DummyEnvironment(JAVASUFFIXES=['.java'],
                               JAVACLASSPATH=path)
        s = SCons.Scanner.Java.JavaScanner()
        deps = s(DummyNode('dummy'), env)
        expected = []
        deps_match(self, deps, expected)


class JavaScannerClasspath(unittest.TestCase):
    def runTest(self):
        env = DummyEnvironment(JAVASUFFIXES=['.java'],
                               JAVACLASSPATH=[test.workpath('classpath.jar')])
        s = SCons.Scanner.Java.JavaScanner()
        deps = s(DummyNode('dummy'), env)
        expected = ['classpath.jar']
        deps_match(self, deps, expected)


class JavaScannerWildcardClasspath(unittest.TestCase):
    def runTest(self):
        env = DummyEnvironment(JAVASUFFIXES=['.java'],
                               JAVACLASSPATH=[test.workpath('*')])
        s = SCons.Scanner.Java.JavaScanner()
        deps = s(DummyNode('dummy'), env)
        expected = ['bootclasspath.jar', 'classpath.jar', 'Test.class']
        deps_match(self, deps, expected)


class JavaScannerDirClasspath(unittest.TestCase):
    def runTest(self):
        env = DummyEnvironment(JAVASUFFIXES=['.java'],
                               JAVACLASSPATH=[test.workpath()])
        s = SCons.Scanner.Java.JavaScanner()
        deps = s(DummyNode('dummy'), env)
        expected = ['Test.class', 'com/Test.class']
        deps_match(self, deps, expected)



if __name__ == "__main__":
    unittest.main()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
