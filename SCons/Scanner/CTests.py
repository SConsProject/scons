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
import TestUnit

import SCons.compat
import SCons.Node.FS
import SCons.Warnings

import SCons.Scanner.C

test = TestCmd.TestCmd(workdir = '')

os.chdir(test.workpath(''))

# create some source files and headers:

test.write('f1.cpp',"""
#ifdef INCLUDE_F2 /* multi-line comment */
#include <f2.h>
#else
#include \"f1.h\"
#endif

int main(void)
{
   return 0;
}
""")

test.write('f2.cpp',"""
#include \"d1/f1.h\"

#if 5UL < 10 && !defined(DUMMY_MACRO) // some comment
    #if NESTED_CONDITION
        #include <d2/f1.h>
    #endif
#else
#include \"f1.h\"
#endif

#import <f4.h>

int main(void)
{
   return 0;
}
""")

test.write('f3.cpp',"""
#include \t "f1.h"
   \t #include "f2.h"
#   \t include "f3-test.h"

#include \t <d1/f1.h>
   \t #include <d1/f2.h>
#   \t include <d1/f3-test.h>

// #include "never.h"

const char* x = "#include <never.h>"

int main(void)
{
   return 0;
}
""")


# for Emacs -> "

test.subdir('d1', ['d1', 'd2'])

headers = ['f1.h','f2.h', 'f3-test.h', 'fi.h', 'fj.h', 'never.h',
           'd1/f1.h', 'd1/f2.h', 'd1/f3-test.h', 'd1/fi.h', 'd1/fj.h',
           'd1/d2/f1.h', 'd1/d2/f2.h', 'd1/d2/f3-test.h',
           'd1/d2/f4.h', 'd1/d2/fi.h', 'd1/d2/fj.h']

for h in headers:
    test.write(h, " ")

test.write('f2.h',"""
#include "fi.h"
""")

test.write('f3-test.h',"""
#include <fj.h>
""")


test.subdir('include', 'subdir', ['subdir', 'include'])

test.write('fa.cpp',"""
#include \"fa.h\"
#include <fb.h>

int main(void)
{
   return 0;
}
""")

test.write(['include', 'fa.h'], "\n")
test.write(['include', 'fb.h'], "\n")
test.write(['subdir', 'include', 'fa.h'], "\n")
test.write(['subdir', 'include', 'fb.h'], "\n")


test.subdir('repository', ['repository', 'include'],
            ['repository', 'src' ])
test.subdir('work', ['work', 'src'])

test.write(['repository', 'include', 'iii.h'], "\n")

test.write(['work', 'src', 'fff.c'], """
#include <iii.h>
#include <jjj.h>

int main(void)
{
    return 0;
}
""")

test.write([ 'work', 'src', 'aaa.c'], """
#include "bbb.h"

int main(void)
{
   return 0;
}
""")

test.write([ 'work', 'src', 'bbb.h'], "\n")

test.write([ 'repository', 'src', 'ccc.c'], """
#include "ddd.h"

int main(void)
{
   return 0;
}
""")

test.write([ 'repository', 'src', 'ddd.h'], "\n")

test.write('f5.c', """\
#include\"f5a.h\"
#include<f5b.h>
""")

test.write("f5a.h", "\n")
test.write("f5b.h", "\n")

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

# define some tests:

class CScannerTestCase1(unittest.TestCase):
    def runTest(self):
        """Find local files with no CPPPATH"""
        env = DummyEnvironment(CPPPATH=[])
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps = s(env.File('f1.cpp'), env, path)
        headers = ['f1.h', 'f2.h']
        deps_match(self, deps, headers)

class CScannerTestCase2(unittest.TestCase):
    def runTest(self):
        """Find a file in a CPPPATH directory"""
        env = DummyEnvironment(CPPPATH=[test.workpath("d1")])
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps = s(env.File('f1.cpp'), env, path)
        headers = ['f1.h', 'd1/f2.h']
        deps_match(self, deps, headers)

class CScannerTestCase3(unittest.TestCase):
    def runTest(self):
        """Find files in explicit subdirectories, ignore missing file"""
        env = DummyEnvironment(CPPPATH=[test.workpath("d1")])
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps = s(env.File('f2.cpp'), env, path)
        headers = ['d1/f1.h', 'f1.h', 'd1/d2/f1.h']
        deps_match(self, deps, headers)

class CScannerTestCase4(unittest.TestCase):
    def runTest(self):
        """Find files in explicit subdirectories"""
        env = DummyEnvironment(CPPPATH=[test.workpath("d1"), test.workpath("d1/d2")])
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps = s(env.File('f2.cpp'), env, path)
        headers =  ['d1/f1.h', 'f1.h', 'd1/d2/f1.h', 'd1/d2/f4.h']
        deps_match(self, deps, headers)

class CScannerTestCase5(unittest.TestCase):
    def runTest(self):
        """Make sure files in repositories will get scanned"""
        env = DummyEnvironment(CPPPATH=[])
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)

        n = env.File('f3.cpp')
        def my_rexists(s):
            s.Tag('rexists_called', 1)
            return SCons.Node._rexists_map[s.GetTag('old_rexists')](s)
        n.Tag('old_rexists', n._func_rexists)
        SCons.Node._rexists_map[3] = my_rexists
        n._func_rexists = 3

        deps = s(n, env, path)

        # Make sure rexists() got called on the file node being
        # scanned, essential for cooperation with VariantDir functionality.
        assert n.GetTag('rexists_called')

        headers =  ['f1.h', 'f2.h', 'f3-test.h',
                    'd1/f1.h', 'd1/f2.h', 'd1/f3-test.h']
        deps_match(self, deps, headers)

class CScannerTestCase6(unittest.TestCase):
    def runTest(self):
        """Find a same-named file in different directories when CPPPATH changes"""
        env1 = DummyEnvironment(CPPPATH=[test.workpath("d1")])
        env2 = DummyEnvironment(CPPPATH=[test.workpath("d1/d2")])
        s = SCons.Scanner.C.CScanner()
        path1 = s.path(env1)
        path2 = s.path(env2)
        deps1 = s(env1.File('f1.cpp'), env1, path1)
        deps2 = s(env2.File('f1.cpp'), env2, path2)
        headers1 =  ['f1.h', 'd1/f2.h']
        headers2 =  ['f1.h', 'd1/d2/f2.h']
        deps_match(self, deps1, headers1)
        deps_match(self, deps2, headers2)

class CScannerTestCase8(unittest.TestCase):
    def runTest(self):
        """Find files in a subdirectory relative to the current directory"""
        env = DummyEnvironment(CPPPATH=["include"])
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps1 = s(env.File('fa.cpp'), env, path)
        env.fs.chdir(env.Dir('subdir'))
        dir = env.fs.getcwd()
        env.fs.chdir(env.Dir(''))
        path = s.path(env, dir)
        deps2 = s(env.File('#fa.cpp'), env, path)
        headers1 =  list(map(test.workpath, ['include/fa.h', 'include/fb.h']))
        headers2 =  ['include/fa.h', 'include/fb.h']
        deps_match(self, deps1, headers1)
        deps_match(self, deps2, headers2)

class CScannerTestCase9(unittest.TestCase):
    def runTest(self):
        """Generate a warning when we can't find a #included file"""
        SCons.Warnings.enableWarningClass(SCons.Warnings.DependencyWarning)
        class TestOut:
            def __call__(self, x):
                self.out = x

        to = TestOut()
        to.out = None
        SCons.Warnings._warningOut = to
        test.write('fa.h','\n')
        fs = SCons.Node.FS.FS(test.workpath(''))
        env = DummyEnvironment(CPPPATH=[])
        env.fs = fs
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps = s(fs.File('fa.cpp'), env, path)

        # Did we catch the warning associated with not finding fb.h?
        assert to.out

        deps_match(self, deps, [ 'fa.h' ])
        test.unlink('fa.h')

class CScannerTestCase10(unittest.TestCase):
    def runTest(self):
        """Find files in the local directory when the scanned file is elsewhere"""
        fs = SCons.Node.FS.FS(test.workpath(''))
        fs.chdir(fs.Dir('include'))
        env = DummyEnvironment(CPPPATH=[])
        env.fs = fs
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        test.write('include/fa.cpp', test.read('fa.cpp'))
        fs.chdir(fs.Dir('..'))
        deps = s(fs.File('#include/fa.cpp'), env, path)
        deps_match(self, deps, [ 'include/fa.h', 'include/fb.h' ])
        test.unlink('include/fa.cpp')

class CScannerTestCase11(unittest.TestCase):
    def runTest(self):
        """Handle dependencies on a derived .h file in a non-existent directory"""
        os.chdir(test.workpath('work'))
        fs = SCons.Node.FS.FS(test.workpath('work'))
        fs.Repository(test.workpath('repository'))

        # Create a derived file in a directory that does not exist yet.
        # This was a bug at one time.
        f1=fs.File('include2/jjj.h')
        f1.builder=1
        env = DummyEnvironment(CPPPATH=['include', 'include2'])
        env.fs = fs
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps = s(fs.File('src/fff.c'), env, path)
        deps_match(self, deps, [ test.workpath('repository/include/iii.h'),
                                 'include2/jjj.h' ])
        os.chdir(test.workpath(''))

class CScannerTestCase12(unittest.TestCase):
    def runTest(self):
        """Find files in VariantDir() directories"""
        os.chdir(test.workpath('work'))
        fs = SCons.Node.FS.FS(test.workpath('work'))
        fs.VariantDir('build1', 'src', 1)
        fs.VariantDir('build2', 'src', 0)
        fs.Repository(test.workpath('repository'))
        env = DummyEnvironment(CPPPATH=[])
        env.fs = fs
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps1 = s(fs.File('build1/aaa.c'), env, path)
        deps_match(self, deps1, [ 'build1/bbb.h' ])
        deps2 = s(fs.File('build2/aaa.c'), env, path)
        deps_match(self, deps2, [ 'src/bbb.h' ])
        deps3 = s(fs.File('build1/ccc.c'), env, path)
        deps_match(self, deps3, [ 'build1/ddd.h' ])
        deps4 = s(fs.File('build2/ccc.c'), env, path)
        deps_match(self, deps4, [ test.workpath('repository/src/ddd.h') ])
        os.chdir(test.workpath(''))

class CScannerTestCase13(unittest.TestCase):
    def runTest(self):
        """Find files in directories named in a substituted environment variable"""
        class SubstEnvironment(DummyEnvironment):
            def subst(self, arg, target=None, source=None, conv=None, test=test):
                if arg == "$blah":
                    return test.workpath("d1")
                else:
                    return arg
        env = SubstEnvironment(CPPPATH=["$blah"])
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps = s(env.File('f1.cpp'), env, path)
        headers = ['f1.h', 'd1/f2.h']
        deps_match(self, deps, headers)

class CScannerTestCase14(unittest.TestCase):
    def runTest(self):
        """Find files when there's no space between "#include" and the name"""
        env = DummyEnvironment(CPPPATH=[])
        s = SCons.Scanner.C.CScanner()
        path = s.path(env)
        deps = s(env.File('f5.c'), env, path)
        headers = ['f5a.h', 'f5b.h']
        deps_match(self, deps, headers)

class CScannerTestCase15(unittest.TestCase):
    def runTest(self):
        """Verify scanner initialization with the suffixes in $CPPSUFFIXES"""
        suffixes = [".c", ".C", ".cxx", ".cpp", ".c++", ".cc",
                    ".h", ".H", ".hxx", ".hpp", ".hh",
                    ".F", ".fpp", ".FPP",
                    ".S", ".spp", ".SPP"]
        env = DummyEnvironment(CPPSUFFIXES = suffixes)
        s = SCons.Scanner.C.CScanner()
        for suffix in suffixes:
            assert suffix in s.get_skeys(env), "%s not in skeys" % suffix


class CConditionalScannerTestCase1(unittest.TestCase):
    def runTest(self):
        """Find local files with no CPPPATH"""
        env = DummyEnvironment(CPPPATH=[])
        s = SCons.Scanner.C.CConditionalScanner()
        path = s.path(env)
        deps = s(env.File('f1.cpp'), env, path)
        headers = ['f1.h']
        deps_match(self, deps, headers)


class CConditionalScannerTestCase2(unittest.TestCase):
    def runTest(self):
        """Find local files with no CPPPATH based on #ifdef"""
        env = DummyEnvironment(CPPPATH=[], CPPDEFINES=["INCLUDE_F2"])
        s = SCons.Scanner.C.CConditionalScanner()
        path = s.path(env)
        deps = s(env.File('f1.cpp'), env, path)
        headers = ['f2.h', 'fi.h']
        deps_match(self, deps, headers)


class CConditionalScannerTestCase3(unittest.TestCase):
    def runTest(self):
        """Find files in explicit subdirectories, ignore missing file"""
        env = DummyEnvironment(
            CPPPATH=[test.workpath("d1")],
            CPPDEFINES=[("NESTED_CONDITION", 1)]
        )
        s = SCons.Scanner.C.CConditionalScanner()
        deps = s(env.File('f2.cpp'), env, s.path(env))
        headers = ['d1/f1.h', 'd1/d2/f1.h']
        deps_match(self, deps, headers)

        # disable nested conditions
        env = DummyEnvironment(
            CPPPATH=[test.workpath("d1")],
            CPPDEFINES=[("NESTED_CONDITION", 0)]
        )
        s = SCons.Scanner.C.CConditionalScanner()
        deps = s(env.File('f2.cpp'), env, s.path(env))
        headers = ['d1/f1.h']
        deps_match(self, deps, headers)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(CScannerTestCase1())
    suite.addTest(CScannerTestCase2())
    suite.addTest(CScannerTestCase3())
    suite.addTest(CScannerTestCase4())
    suite.addTest(CScannerTestCase5())
    suite.addTest(CScannerTestCase6())
    suite.addTest(CScannerTestCase8())
    suite.addTest(CScannerTestCase9())
    suite.addTest(CScannerTestCase10())
    suite.addTest(CScannerTestCase11())
    suite.addTest(CScannerTestCase12())
    suite.addTest(CScannerTestCase13())
    suite.addTest(CScannerTestCase14())
    suite.addTest(CScannerTestCase15())
    suite.addTest(CConditionalScannerTestCase1())
    suite.addTest(CConditionalScannerTestCase2())
    suite.addTest(CConditionalScannerTestCase3())
    return suite

if __name__ == "__main__":
    TestUnit.run(suite())

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
