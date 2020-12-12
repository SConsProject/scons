#!/usr/bin/env python
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
#


"""
Test the --cache-debug option to see if it prints the expected messages.

Note that we don't check for the "race condition" message when someone
else's build populates the CacheDir with a file in between the time we
to build it because it doesn't exist in the CacheDir, and the time our
build of the file completes and we push it out.
"""

import TestSCons

test = TestSCons.TestSCons(match=TestSCons.match_re)

test.subdir('cache', 'src')

cache = test.workpath('cache')
debug_out = test.workpath('cache-debug.out')



test.write(['src', 'SConstruct'], """\
DefaultEnvironment(tools=[])
CacheDir(r'%(cache)s')
SConscript('SConscript')
""" % locals())

test.write(['src', 'SConscript'], """\
def cat(env, source, target):
    target = str(target[0])
    with open('cat.out', 'a') as f:
        f.write(target + "\\n")
    with open(target, "w") as f:
        for src in source:
            with open(str(src), "r") as f2:
                f.write(f2.read())
env = Environment(tools=[], BUILDERS={'Cat':Builder(action=cat)})
env.Cat('aaa.out', 'aaa.in')
env.Cat('bbb.out', 'bbb.in')
env.Cat('ccc.out', 'ccc.in')
env.Cat('all', ['aaa.out', 'bbb.out', 'ccc.out'])
""")

test.write(['src', 'aaa.in'], "aaa.in\n")
test.write(['src', 'bbb.in'], "bbb.in\n")
test.write(['src', 'ccc.in'], "ccc.in\n")



# Test for messages about files not being in CacheDir, with -n (don't
# actually build or push) and sendinig the message to a file.

expect = \
r"""cat\(\["aaa.out"\], \["aaa.in"\]\)
cat\(\["bbb.out"\], \["bbb.in"\]\)
cat\(\["ccc.out"\], \["ccc.in"\]\)
cat\(\["all"\], \["aaa.out", "bbb.out", "ccc.out"\]\)
"""

test.run(chdir='src',
         arguments='-n -Q --cache-debug=%s .' % debug_out,
         stdout=expect)

expect = \
r"""CacheRetrieve\(aaa.out\):  [0-9a-fA-F]+ not in cache
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
CacheRetrieve\(bbb.out\):  [0-9a-fA-F]+ not in cache
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
CacheRetrieve\(ccc.out\):  [0-9a-fA-F]+ not in cache
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
CacheRetrieve\(all\):  [0-9a-fA-F]+ not in cache
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
"""

test.must_match(debug_out, expect, mode='r')



# Test for messages about actually pushing to the cache, without -n
# and to standard ouput.

expect = \
r"""CacheRetrieve\(aaa.out\):  [0-9a-fA-F]+ not in cache
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
cat\(\["aaa.out"\], \["aaa.in"\]\)
CachePush\(aaa.out\):  pushing to [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
CacheRetrieve\(bbb.out\):  [0-9a-fA-F]+ not in cache
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
cat\(\["bbb.out"\], \["bbb.in"\]\)
CachePush\(bbb.out\):  pushing to [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
CacheRetrieve\(ccc.out\):  [0-9a-fA-F]+ not in cache
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
cat\(\["ccc.out"\], \["ccc.in"\]\)
CachePush\(ccc.out\):  pushing to [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
CacheRetrieve\(all\):  [0-9a-fA-F]+ not in cache
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
cat\(\["all"\], \["aaa.out", "bbb.out", "ccc.out"\]\)
CachePush\(all\):  pushing to [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
"""

test.run(chdir='src',
         arguments='-Q --cache-debug=- .',
         stdout=expect)



# Clean up the local targets.

test.run(chdir='src', arguments='-c --cache-debug=%s .' % debug_out)
test.unlink(['src', 'cat.out'])



# Test for messages about retrieving files from CacheDir, with -n
# and sending the messages to standard output.

expect = \
r"""Retrieved `aaa.out' from cache
CacheRetrieve\(aaa.out\):  retrieved from [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
Retrieved `bbb.out' from cache
CacheRetrieve\(bbb.out\):  retrieved from [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
Retrieved `ccc.out' from cache
CacheRetrieve\(ccc.out\):  retrieved from [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
Retrieved `all' from cache
CacheRetrieve\(all\):  retrieved from [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
"""

test.run(chdir='src',
         arguments='-n -Q --cache-debug=- .',
         stdout=expect)



# And finally test for message about retrieving file from CacheDir
# *without* -n and sending the message to a file.

expect = \
r"""Retrieved `aaa.out' from cache
Retrieved `bbb.out' from cache
Retrieved `ccc.out' from cache
Retrieved `all' from cache
"""

test.run(chdir='src',
         arguments='-Q --cache-debug=%s .' % debug_out,
         stdout=expect)

expect = \
r"""CacheRetrieve\(aaa.out\):  retrieved from [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
CacheRetrieve\(bbb.out\):  retrieved from [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
CacheRetrieve\(ccc.out\):  retrieved from [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
CacheRetrieve\(all\):  retrieved from [0-9a-fA-F]+
requests: [0-9]+, hits: [0-9]+, misses: [0-9]+, hit rate: [0-9]+\.[0-9]{2,}%
"""

test.must_match(debug_out, expect, mode='r')



test.pass_test()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
