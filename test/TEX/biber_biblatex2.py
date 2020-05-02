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

r"""
Test creation of a Tex document that uses the biblatex package
It uses the default backend, could be bibtex or biber. 
Require both be installed

Test courtesy Rob Managan.
"""

import subprocess

import TestSCons

test = TestSCons.TestSCons()

latex = test.where_is('pdflatex')
if not latex:
    test.skip_test("Could not find 'pdflatex'; skipping test.\n")

biber = test.where_is('biber')
if not biber:
    test.skip_test("Could not find 'biber'; skipping test.\n")

bibtex = test.where_is('bibtex')
if not bibtex:
    test.skip_test("Could not find 'bibtex'; skipping test.\n")

cp = subprocess.run('kpsewhich biblatex.sty', shell=True)
if cp.returncode:
    test.skip_test("biblatex.sty not installed; skipping test(s).\n")


test.write(['SConstruct'], """\
import os
env = Environment(ENV=os.environ)
main_output = env.PDF('bibertest.tex')
""")


sources_bib_content = r"""
@book{mybook,
  title={Title},
  author={Author, A},
  year={%s},
  publisher={Publisher},
}
"""
test.write(['ref.bib'],sources_bib_content % '2013' )

sources_tex_content = r"""
\documentclass{article}

\usepackage{biblatex}
\addbibresource{ref.bib}

\begin{document}

Hello. This is %s boring.
\cite{mybook}
And even more boring.

\printbibliography
\end{document}
"""
test.write(['bibertest.tex'], sources_tex_content % "")


test.run()


# All (?) the files we expect will get created in the docs directory
files = [
    'bibertest.aux',
    'bibertest.bbl',
    'bibertest.blg',
    'bibertest.fls',
    'bibertest.log',
    'bibertest.pdf',
    'bibertest.run.xml',
]


for f in files:
    test.must_exist([ f])

pdf_output_1 = test.read('bibertest.pdf')


# Change tex, but don't change bib. In this case, pdf should still be rebuilt.
test.write(['bibertest.tex'], sources_tex_content % "very")
test.run()
pdf_output_1a = test.read('bibertest.pdf')
# If the PDF file is the same as it was previously, then it didn't
# pick up the change in the tex file, so fail.
test.fail_test(pdf_output_1 == pdf_output_1a)


# Change bib.
test.write(['bibertest.tex'], sources_tex_content % "")
test.write(['ref.bib'],sources_bib_content % '1982')

test.run()

pdf_output_2 = test.read('bibertest.pdf')

pdf_output_1 = test.normalize_pdf(pdf_output_1)
pdf_output_2 = test.normalize_pdf(pdf_output_2)

# If the PDF file is the same as it was previously, then it didn't
# pick up the change from 1981 to 1982, so fail.
test.fail_test(pdf_output_1 == pdf_output_2)

test.pass_test()
