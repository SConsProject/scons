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

__revision__ = "__FILE__ __REVISION__ __DATE__ __DEVELOPER__"

import unittest
import random
import math
import sys
import time
import os

import TestUnit

import SCons.Job


def get_cpu_nums():
    # Linux, Unix and MacOS:
    if hasattr( os, "sysconf" ):
        if "SC_NPROCESSORS_ONLN" in os.sysconf_names:
            # Linux & Unix:
            ncpus = os.sysconf( "SC_NPROCESSORS_ONLN" )
        if isinstance(ncpus, int) and ncpus > 0:
            return ncpus
        else: # OSX:
            return int( os.popen2( "sysctl -n hw.ncpu")[1].read() )
    # Windows:
    if "NUMBER_OF_PROCESSORS" in os.environ:
        ncpus = int(os.environ["NUMBER_OF_PROCESSORS"])
    if ncpus > 0:
        return ncpus
    return 1 # Default

# a large number
num_sines = 500

# how many parallel jobs to perform for the test
num_jobs = get_cpu_nums()*2

# in case we werent able to detect num cpus for this test
# just make a hardcoded suffcient large number, though not future proof
if num_jobs == 2:
    num_jobs = 33

# how many tasks to perform for the test
num_tasks = num_jobs*5

class DummyLock(object):
    """fake lock class to use if threads are not supported"""
    def acquire(self):
        pass

    def release(self):
        pass

class NoThreadsException(Exception):
    """raised by the ParallelTestCase if threads are not supported"""

    def __str__(self):
        return "the interpreter doesn't support threads"

class Task(object):
    """A dummy task class for testing purposes."""

    def __init__(self, i, taskmaster):
        self.i = i
        self.taskmaster = taskmaster
        self.was_executed = 0
        self.was_prepared = 0

    def prepare(self):
        self.was_prepared = 1

    def _do_something(self):
        pass

    def needs_execute(self):
        return True

    def execute(self):
        self.taskmaster.test_case.assertTrue(self.was_prepared,
                                  "the task wasn't prepared")

        self.taskmaster.guard.acquire()
        self.taskmaster.begin_list.append(self.i)
        self.taskmaster.guard.release()

        # while task is executing, represent this in the parallel_list
        # and then turn it off
        self.taskmaster.parallel_list[self.i] = 1
        self._do_something()
        self.taskmaster.parallel_list[self.i] = 0

        # check if task was executing while another was also executing
        for j in range(1, self.taskmaster.num_tasks):
            if self.taskmaster.parallel_list[j + 1] == 1:
                self.taskmaster.found_parallel = True
                break

        self.was_executed = 1

        self.taskmaster.guard.acquire()
        self.taskmaster.end_list.append(self.i)
        self.taskmaster.guard.release()

    def executed(self):
        self.taskmaster.num_executed = self.taskmaster.num_executed + 1

        self.taskmaster.test_case.assertTrue(self.was_prepared,
                                  "the task wasn't prepared")
        self.taskmaster.test_case.assertTrue(self.was_executed,
                                  "the task wasn't really executed")
        self.taskmaster.test_case.assertTrue(isinstance(self, Task),
                                  "the task wasn't really a Task instance")

    def failed(self):
        self.taskmaster.num_failed = self.taskmaster.num_failed + 1
        self.taskmaster.stop = 1
        self.taskmaster.test_case.assertTrue(self.was_prepared,
                                  "the task wasn't prepared")

    def postprocess(self):
        self.taskmaster.num_postprocessed = self.taskmaster.num_postprocessed + 1

    def exception_set(self):
        pass

class RandomTask(Task):
    def _do_something(self):
        # do something that will take some random amount of time:
        for i in range(random.randrange(0, 100 + num_sines, 1)):
            x = math.sin(i)
        time.sleep(0.01)

class ExceptionTask(object):
    """A dummy task class for testing purposes."""

    def __init__(self, i, taskmaster):
        self.taskmaster = taskmaster
        self.was_prepared = 0

    def prepare(self):
        self.was_prepared = 1

    def needs_execute(self):
        return True

    def execute(self):
        raise Exception

    def executed(self):
        self.taskmaster.num_executed = self.taskmaster.num_executed + 1

        self.taskmaster.test_case.assertTrue(self.was_prepared,
                                  "the task wasn't prepared")
        self.taskmaster.test_case.assertTrue(self.was_executed,
                                  "the task wasn't really executed")
        self.taskmaster.test_case.assertTrue(self.__class__ is Task,
                                  "the task wasn't really a Task instance")

    def failed(self):
        self.taskmaster.num_failed = self.taskmaster.num_failed + 1
        self.taskmaster.stop = 1
        self.taskmaster.test_case.assertTrue(self.was_prepared,
                                  "the task wasn't prepared")

    def postprocess(self):
        self.taskmaster.num_postprocessed = self.taskmaster.num_postprocessed + 1

    def exception_set(self):
        self.taskmaster.exception_set()

class Taskmaster(object):
    """A dummy taskmaster class for testing the job classes."""

    def __init__(self, n, test_case, Task):
        """n is the number of dummy tasks to perform."""

        self.test_case = test_case
        self.stop = None
        self.num_tasks = n
        self.num_iterated = 0
        self.num_executed = 0
        self.num_failed = 0
        self.num_postprocessed = 0
        self.parallel_list = [0] * (n+1)
        self.found_parallel = False
        self.Task = Task

        # 'guard' guards 'task_begin_list' and 'task_end_list'
        try:
            import threading
            self.guard = threading.Lock()
        except:
            self.guard = DummyLock()

        # keep track of the order tasks are begun in
        self.begin_list = []

        # keep track of the order tasks are completed in
        self.end_list = []

    def next_task(self):
        if self.stop or self.all_tasks_are_iterated():
            return None
        else:
            self.num_iterated = self.num_iterated + 1
            return self.Task(self.num_iterated, self)

    def all_tasks_are_executed(self):
        return self.num_executed == self.num_tasks

    def all_tasks_are_iterated(self):
        return self.num_iterated == self.num_tasks

    def all_tasks_are_postprocessed(self):
        return self.num_postprocessed == self.num_tasks

    def tasks_were_serial(self):
        """analyze the task order to see if they were serial"""
        return not self.found_parallel

    def exception_set(self):
        pass

    def cleanup(self):
        pass

SaveThreadPool = None
ThreadPoolCallList = []

class ParallelTestCase(unittest.TestCase):
    def runTest(self):
        """test parallel jobs"""

        try:
            import threading
        except:
            raise NoThreadsException()

        taskmaster = Taskmaster(num_tasks, self, RandomTask)
        jobs = SCons.Job.Jobs(num_jobs, taskmaster)
        jobs.run()

        self.assertTrue(not taskmaster.tasks_were_serial(),
                        "the tasks were not executed in parallel")
        self.assertTrue(taskmaster.all_tasks_are_executed(),
                        "all the tests were not executed")
        self.assertTrue(taskmaster.all_tasks_are_iterated(),
                        "all the tests were not iterated over")
        self.assertTrue(taskmaster.all_tasks_are_postprocessed(),
                        "all the tests were not postprocessed")
        self.assertFalse(taskmaster.num_failed,
                    "some task(s) failed to execute")

        # Verify that parallel jobs will pull all of the completed tasks
        # out of the queue at once, instead of one by one.  We do this by
        # replacing the default ThreadPool class with one that records the
        # order in which tasks are put() and get() to/from the pool, and
        # which sleeps a little bit before call get() to let the initial
        # tasks complete and get their notifications on the resultsQueue.

        class SleepTask(Task):
            def _do_something(self):
                time.sleep(random.uniform(0, 0.9))

        global SaveThreadPool
        SaveThreadPool = SCons.Job.ThreadPool

        class WaitThreadPool(SaveThreadPool):
            def put(self, task):
                ThreadPoolCallList.append('put(%s)' % task.i)
                return SaveThreadPool.put(self, task)
            def get(self, block):
                result = SaveThreadPool.get(self, block)
                ThreadPoolCallList.append('get(%s)' % result[0].i)
                return result

        SCons.Job.ThreadPool = WaitThreadPool

        try:
            taskmaster = Taskmaster(3, self, SleepTask)
            jobs = SCons.Job.Jobs(2, taskmaster)
            jobs.run()

            # The key here is that we get(1) and get(2) from the
            # resultsQueue before we put(3), but get(1) and get(2) can
            # be in either order depending on how the first two parallel
            # tasks get scheduled by the operating system.
            expect = [
                ['put(1)', 'put(2)', 'get(1)', 'get(2)', 'put(3)', 'get(3)'],
                ['put(1)', 'put(2)', 'get(1)', 'put(3)', 'get(2)', 'get(3)'],
                ['put(1)', 'put(2)', 'get(1)', 'put(3)', 'get(3)', 'get(2)'],
                ['put(1)', 'put(2)', 'get(2)', 'get(1)', 'put(3)', 'get(3)'],
                ['put(1)', 'put(2)', 'get(2)', 'put(3)', 'get(1)', 'get(3)'],
                ['put(1)', 'put(2)', 'get(2)', 'put(3)', 'get(3)', 'get(1)'],
            ]
            assert ThreadPoolCallList in expect, ThreadPoolCallList

        finally:
            SCons.Job.ThreadPool = SaveThreadPool

class SerialTestCase(unittest.TestCase):
    def runTest(self):
        """test a serial job"""

        taskmaster = Taskmaster(num_tasks, self, RandomTask)
        jobs = SCons.Job.Jobs(1, taskmaster)
        jobs.run()

        self.assertTrue(taskmaster.tasks_were_serial(),
                        "the tasks were not executed in series")
        self.assertTrue(taskmaster.all_tasks_are_executed(),
                        "all the tests were not executed")
        self.assertTrue(taskmaster.all_tasks_are_iterated(),
                        "all the tests were not iterated over")
        self.assertTrue(taskmaster.all_tasks_are_postprocessed(),
                        "all the tests were not postprocessed")
        self.assertFalse(taskmaster.num_failed,
                    "some task(s) failed to execute")

class NoParallelTestCase(unittest.TestCase):
    def runTest(self):
        """test handling lack of parallel support"""
        def NoParallel(tm, num, stack_size):
            raise NameError
        save_Parallel = SCons.Job.Parallel
        SCons.Job.Parallel = NoParallel
        try:
            taskmaster = Taskmaster(num_tasks, self, RandomTask)
            jobs = SCons.Job.Jobs(2, taskmaster)
            self.assertTrue(jobs.num_jobs == 1,
                            "unexpected number of jobs %d" % jobs.num_jobs)
            jobs.run()
            self.assertTrue(taskmaster.tasks_were_serial(),
                            "the tasks were not executed in series")
            self.assertTrue(taskmaster.all_tasks_are_executed(),
                            "all the tests were not executed")
            self.assertTrue(taskmaster.all_tasks_are_iterated(),
                            "all the tests were not iterated over")
            self.assertTrue(taskmaster.all_tasks_are_postprocessed(),
                            "all the tests were not postprocessed")
            self.assertFalse(taskmaster.num_failed,
                        "some task(s) failed to execute")
        finally:
            SCons.Job.Parallel = save_Parallel


class SerialExceptionTestCase(unittest.TestCase):
    def runTest(self):
        """test a serial job with tasks that raise exceptions"""

        taskmaster = Taskmaster(num_tasks, self, ExceptionTask)
        jobs = SCons.Job.Jobs(1, taskmaster)
        jobs.run()

        self.assertFalse(taskmaster.num_executed,
                    "a task was executed")
        self.assertTrue(taskmaster.num_iterated == 1,
                    "exactly one task should have been iterated")
        self.assertTrue(taskmaster.num_failed == 1,
                    "exactly one task should have failed")
        self.assertTrue(taskmaster.num_postprocessed == 1,
                    "exactly one task should have been postprocessed")

class ParallelExceptionTestCase(unittest.TestCase):
    def runTest(self):
        """test parallel jobs with tasks that raise exceptions"""

        taskmaster = Taskmaster(num_tasks, self, ExceptionTask)
        jobs = SCons.Job.Jobs(num_jobs, taskmaster)
        jobs.run()

        self.assertFalse(taskmaster.num_executed,
                    "a task was executed")
        self.assertTrue(taskmaster.num_iterated >= 1,
                    "one or more task should have been iterated")
        self.assertTrue(taskmaster.num_failed >= 1,
                    "one or more tasks should have failed")
        self.assertTrue(taskmaster.num_postprocessed >= 1,
                    "one or more tasks should have been postprocessed")

#---------------------------------------------------------------------
# Above tested Job object with contrived Task and Taskmaster objects.
# Now test Job object with actual Task and Taskmaster objects.

import SCons.Taskmaster
import SCons.Node
import time

class DummyNodeInfo(object):
    def update(self, obj):
        pass

class testnode (SCons.Node.Node):
    def __init__(self):
        SCons.Node.Node.__init__(self)
        self.expect_to_be = SCons.Node.executed
        self.ninfo = DummyNodeInfo()

class goodnode (testnode):
    def __init__(self):
        SCons.Node.Node.__init__(self)
        self.expect_to_be = SCons.Node.up_to_date
        self.ninfo = DummyNodeInfo()

class slowgoodnode (goodnode):
    def prepare(self):
        # Delay to allow scheduled Jobs to run while the dispatcher
        # sleeps.  Keep this short because it affects the time taken
        # by this test.
        time.sleep(0.15)
        goodnode.prepare(self)

class badnode (goodnode):
    def __init__(self):
        goodnode.__init__(self)
        self.expect_to_be = SCons.Node.failed
    def build(self, **kw):
        raise Exception('badnode exception')

class slowbadnode (badnode):
    def build(self, **kw):
        # Appears to take a while to build, allowing faster builds to
        # overlap.  Time duration is not especially important, but if
        # it is faster than slowgoodnode then these could complete
        # while the scheduler is sleeping.
        time.sleep(0.05)
        raise Exception('slowbadnode exception')

class badpreparenode (badnode):
    def prepare(self):
        raise Exception('badpreparenode exception')

class _SConsTaskTest(unittest.TestCase):

    def _test_seq(self, num_jobs):
        for node_seq in [
            [goodnode],
            [badnode],
            [slowbadnode],
            [slowgoodnode],
            [badpreparenode],
            [goodnode, badnode],
            [slowgoodnode, badnode],
            [goodnode, slowbadnode],
            [goodnode, goodnode, goodnode, slowbadnode],
            [goodnode, slowbadnode, badpreparenode, slowgoodnode],
            [goodnode, slowbadnode, slowgoodnode, badnode]
            ]:

            self._do_test(num_jobs, node_seq)

    def _do_test(self, num_jobs, node_seq):

        testnodes = []
        for tnum in range(num_tasks):
            testnodes.append(node_seq[tnum % len(node_seq)]())

        taskmaster = SCons.Taskmaster.Taskmaster(testnodes,
                                                 tasker=SCons.Taskmaster.AlwaysTask)

        jobs = SCons.Job.Jobs(num_jobs, taskmaster)

        # Exceptions thrown by tasks are not actually propagated to
        # this level, but are instead stored in the Taskmaster.

        jobs.run()

        # Now figure out if tests proceeded correctly.  The first test
        # that fails will shutdown the initiation of subsequent tests,
        # but any tests currently queued for execution will still be
        # processed, and any tests that completed before the failure
        # would have resulted in new tests being queued for execution.

        # Apply the following operational heuristics of Job.py:
        #  0) An initial jobset of tasks will be queued before any
        #     good/bad results are obtained (from "execute" of task in
        #     thread).
        #  1) A goodnode will complete immediately on its thread and
        #     allow another node to be queued for execution.
        #  2) A badnode will complete immediately and suppress any
        #     subsequent execution queuing, but all currently queued
        #     tasks will still be processed.
        #  3) A slowbadnode will fail later.  It will block slots in
        #     the job queue.  Nodes that complete immediately will
        #     allow other nodes to be queued in their place, and this
        #     will continue until either (#2) above or until all job
        #     slots are filled with slowbadnode entries.

        # One approach to validating this test would be to try to
        # determine exactly how many nodes executed, how many didn't,
        # and the results of each, and then to assert failure on any
        # mismatch (including the total number of built nodes).
        # However, while this is possible to do for a single-processor
        # system, it is nearly impossible to predict correctly for a
        # multi-processor system and still test the characteristics of
        # delayed execution nodes.  Stated another way, multithreading
        # is inherently non-deterministic unless you can completely
        # characterize the entire system, and since that's not
        # possible here, we shouldn't try.

        # Therefore, this test will simply scan the set of nodes to
        # see if the node was executed or not and if it was executed
        # that it obtained the expected value for that node
        # (i.e. verifying we don't get failure crossovers or
        # mislabelling of results).

        for N in testnodes:
            state = N.get_state()
            self.assertTrue(state in [SCons.Node.no_state, N.expect_to_be],
                            "Node %s got unexpected result: %s" % (N, state))

        self.assertTrue([N for N in testnodes if N.get_state()],
                        "no nodes ran at all.")


class SerialTaskTest(_SConsTaskTest):
    def runTest(self):
        """test serial jobs with actual Taskmaster and Task"""
        self._test_seq(1)


class ParallelTaskTest(_SConsTaskTest):
    def runTest(self):
        """test parallel jobs with actual Taskmaster and Task"""
        self._test_seq(num_jobs)



#---------------------------------------------------------------------

def suite():
    suite = unittest.TestSuite()
    suite.addTest(ParallelTestCase())
    suite.addTest(SerialTestCase())
    suite.addTest(NoParallelTestCase())
    suite.addTest(SerialExceptionTestCase())
    suite.addTest(ParallelExceptionTestCase())
    suite.addTest(SerialTaskTest())
    suite.addTest(ParallelTaskTest())
    return suite

if __name__ == "__main__":
    runner = TestUnit.cli.get_runner()
    result = runner().run(suite())
    if (len(result.failures) == 0
        and len(result.errors) == 1
        and isinstance(result.errors[0][0], SerialTestCase)
        and isinstance(result.errors[0][1][0], NoThreadsException)):
        sys.exit(2)
    elif not result.wasSuccessful():
        sys.exit(1)

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
