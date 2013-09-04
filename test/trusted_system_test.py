import contextlib
import itertools
import os
import re
import subprocess
import tempfile
import unittest

import libvtd.node
import libvtd.trusted_system

###############################################################################
# Helper functions


@contextlib.contextmanager
def TempInput(data):
    temp = tempfile.NamedTemporaryFile(delete=False)
    temp.write('\n'.join(data))
    temp.close()
    yield temp.name
    os.unlink(temp.name)


def FirstTextMatch(node_list, search_regex):
    """Find the first Node in node_list which matches search_regex.

    Args:
        node_list: A container of Node objects.
        search_regex: A regular expression to match with the Node object.

    Returns:
        The first Node object in node_list which matches search_regex, or None
        if none were found.
    """
    regex = re.compile(search_regex)
    for node in node_list:
        if regex.search(node.text):
            return node
    return None


def DueDate(date_string):
    """Parse date_string into a VTD due date, using the VTD machinery.

    This is handy because date-only due dates, such as "2013-08-25", get parsed
    into end-of-day due times.  We don't want to worry about whether it's
    "2013-08-25 23:59:59", "2013-08-25 23:59", or even something else.

    Args:
        date_string: A string which a VTD Node would recognize as a date/time.

    Returns:
        A datetime.datetime object giving the equivalent VTD due date.
    """
    node = libvtd.node.NextAction()
    node.AbsorbText('<{}'.format(date_string))
    return node.due_date

###############################################################################
# Test code


class TestTrustedSystemBaseClass(unittest.TestCase):

    def setUp(self):
        self.trusted_system = libvtd.trusted_system.TrustedSystem()

    def addAnonymousFile(self, data):
        with TempInput(data) as file_name:
            self.trusted_system.AddFile(file_name)


class TestTrustedSystemNextActions(TestTrustedSystemBaseClass):
    def testInheritContext(self):
        self.addAnonymousFile([
            "= Section @test =",
            "",
            "@ Top-level action",
            "# Project",
            "  * Comment (which is neither a NextAction nor a blocker)",
            "  @ Inherited action",
            "- Project which cancels context @!test @x",
            "  @ Action which should show up only under 'x'",
        ])
        # Check @test actions
        self.trusted_system.SetContexts(include=['test'])
        next_actions = self.trusted_system.NextActions()
        self.assertItemsEqual(['Top-level action', 'Inherited action'],
                              [x.text for x in next_actions])
        # Check @x actions
        self.trusted_system.SetContexts(include=['x'])
        next_actions = self.trusted_system.NextActions()
        self.assertItemsEqual(["Action which should show up only under 'x'"],
                              [x.text for x in next_actions])
        # Get the actions; check their priorities... somehow!

    def testInheritPriority(self):
        self.addAnonymousFile([
            "= Section @p:4 @test =",
            "",
            "@ Priority 4 task",
            "- Unordered Project @p:2",
            "  @ Priority 2 task",
            "  @ Priority 0 task @p:0",
            "# Ordered project (implicit priority 4)",
            "  @ Do ordered project",
        ])
        self.trusted_system.SetContexts(include=['test'])
        next_actions = self.trusted_system.NextActions()
        self.assertEqual(4, len(next_actions))
        self.assertEqual(0, FirstTextMatch(next_actions, "Pri.*0").priority)
        self.assertEqual(2, FirstTextMatch(next_actions, "Pri.*2").priority)
        self.assertEqual(4, FirstTextMatch(next_actions, "Pri.*4").priority)
        self.assertEqual(4, FirstTextMatch(next_actions, "Do ord").priority)

    def testInheritDueDate(self):
        self.addAnonymousFile([
            "= Section @test =",
            "",
            "@ No due date",
            "",
            "- Project with due date <2013-08-25",
            "  @ Inherits due date",
            "  @ Has own due date <2013-08-23",
            "  @ Use earliest of all due dates <2013-08-27",
            "",
            "= Section with due date @test <2013-07-25 =",
            "",
            "@ Get section's due date",
            "",
            "- Project without explicit due date",
            "  @ Multi-level due date inheritance",
        ])
        self.trusted_system.SetContexts(include=['test'])
        next_actions = self.trusted_system.NextActions()
        self.assertEqual(6, len(next_actions))
        self.assertIsNone(FirstTextMatch(next_actions, "^No due dat").due_date)
        self.assertEqual(DueDate("2013-08-25"),
                         FirstTextMatch(next_actions, "^Inherits du").due_date)
        self.assertEqual(DueDate("2013-08-23"),
                         FirstTextMatch(next_actions, "^Has own due").due_date)
        self.assertEqual(DueDate("2013-08-25"),
                         FirstTextMatch(next_actions, "^Use earlies").due_date)
        self.assertEqual(DueDate("2013-07-25"),
                         FirstTextMatch(next_actions, "^Get section").due_date)
        self.assertEqual(DueDate("2013-07-25"),
                         FirstTextMatch(next_actions, "^Multi-level").due_date)
        # Don't forget to test that the implicit ready_date gets inherited.
        self.assertEqual(DueDate("2013-07-24"),
                         FirstTextMatch(next_actions, "^Multi-lev").ready_date)

    def testIgnoreRecurs(self):
        self.addAnonymousFile([
            "= Section @test =",
            "",
            "@ Regular action",
            "@ Recurring action",
            "  EVERY day",
        ])
        self.trusted_system.SetContexts(include=['test'])
        self.assertItemsEqual(
            ['Regular action'],
            [x.text for x in self.trusted_system.NextActions()])

    def testDone(self):
        self.addAnonymousFile([
            "= @@Test section =",
            "",
            "@ Finished action (DONE)",
            "@ Unfinished action",
        ])
        self.trusted_system.SetContexts(include=['test'])
        self.assertItemsEqual(
            ['Unfinished action'],
            [x.text for x in self.trusted_system.NextActions()])

    def testRefresh(self):
        self.trusted_system.SetContexts(include=['test'])

        # First iteration of test file: just one action.
        temp = tempfile.NamedTemporaryFile(delete=False)
        temp.write('\n'.join([
            "= @@Test section =",
            "",
            "@ first action"
        ]))
        temp.close()
        self.trusted_system.AddFile(temp.name)
        self.assertLess(os.path.getmtime(temp.name),
                        self.trusted_system.last_refreshed)
        self.assertItemsEqual(
            ['first action'],
            [x.text for x in self.trusted_system.NextActions()])

        # Add text to the file, but make the system think it's already been
        # updated; this new action should not show up.
        with open(temp.name, 'a') as temp_file:
            temp_file.write('\n@ next action')
        time_interval = 60  # Adjust timestamps by this (arbitrary) amount.
        self.trusted_system.last_refreshed += time_interval
        self.trusted_system.Refresh()
        self.assertItemsEqual(
            ['first action'],
            [x.text for x in self.trusted_system.NextActions()])

        # Refresh() should update the timestamp and find the new action.
        self.trusted_system.last_refreshed -= 2 * time_interval
        self.trusted_system.Refresh()
        self.assertLess(os.path.getmtime(temp.name),
                        self.trusted_system.last_refreshed)
        self.assertItemsEqual(
            ['first action', 'next action'],
            [x.text for x in self.trusted_system.NextActions()])

        # Clean up after ourselves.
        os.unlink(temp.name)


class TestTrustedSystemContexts(TestTrustedSystemBaseClass):
    def testListContexts(self):
        self.addAnonymousFile([
            "@ E.T. @@phone @@home",                # home, phone
            "@ Go @@home",                          # home
            "@ @@Work harder",                      # work
            "@ @@Phone @@Mom and @@Dad",            # dad, mom, phone
            "@ Wash the dishes @home",              # home
            "# Ordered @@work project",
            "  @ First step, which is unblocked.",  # work
            "  @ Second step, which is blocked.",
        ])
        expected_contexts = [
            ('home', 3),
            ('phone', 2),
            ('work', 2),
            ('dad', 1),
            ('mom', 1),
        ]
        for (expected, actual) in itertools.izip_longest(
                expected_contexts, self.trusted_system.ContextList()):
            self.assertEqual(expected, actual)

    def testContextParsing(self):
        self.trusted_system.SetContexts(include=['phone', 'online', 'bug'])
        self.addAnonymousFile([
            "@ @@Phone mom",
            "@ Pay rent @online",
            "@ Fix @@bug: colons",
            "@ Fix SEGV @@bug!!",
        ])
        # Double-@ sign should leave the word intact; single-@ sign should be
        # stripped out.  We implicitly check that the contexts get set by
        # checking that we see the actions we expect.
        self.assertItemsEqual(
            ['Phone mom', 'Pay rent', 'Fix bug: colons', 'Fix SEGV bug!!'],
            [x.text for x in self.trusted_system.NextActions()])


class TestTrustedSystemPatches(TestTrustedSystemBaseClass):
    """Nodes should return a patch to perform various actions."""
    def testDiffToggleTodo(self):
        self.trusted_system.SetContexts(include=['test'])
        with TempInput(['@ @@test patches', '']) as file_name:
            self.trusted_system.AddFile(file_name)
            self.assertItemsEqual(
                ['test patches'],
                [x.text for x in self.trusted_system.NextActions()])
            action = FirstTextMatch(self.trusted_system.NextActions(), "^test")

            # Get and apply the patch to check this off as DONE.
            patch = action.Patch(libvtd.node.Actions.MarkDONE)
            DEVNULL = open('/dev/null', 'w')
            subprocess.Popen('patch {}'.format(action.file_name),
                             shell=True, stdout=DEVNULL, stdin=subprocess.PIPE
                             ).communicate(patch)
            self.trusted_system.Refresh(force=True)
            self.assertItemsEqual([], self.trusted_system.NextActions())

            # Apply the patch in reverse; the action should reappear.
            subprocess.Popen('patch -R {}'.format(action.file_name),
                             shell=True, stdout=DEVNULL,
                             stdin=subprocess.PIPE).communicate(patch)
            self.trusted_system.Refresh(force=True)
            self.assertItemsEqual(
                ['test patches'],
                [x.text for x in self.trusted_system.NextActions()])


class TestTrustedSystemProjects(TestTrustedSystemBaseClass):
    def testExplicitBlockers(self):
        self.addAnonymousFile([
            "= @@Test section =",
            "",
            "@ Second action @after:firstAction",
            "@ First action #firstAction",
            "",
            "@ Blocking action #blocker (DONE)",
            "@ Newly unblocked action @after:blocker",
            "",
            "@ Blocker nonexistent @after:nothing",
            "",
            "- Blocked project @after:firstAction",
            "  @ An action I should not see",
        ])
        self.trusted_system.SetContexts(include=['test'])
        self.assertItemsEqual(
            ['First action', 'Newly unblocked action', 'Blocker nonexistent'],
            [x.text for x in self.trusted_system.NextActions()])

    def testOrderedProjects(self):
        self.addAnonymousFile([
            "= @@Test section =",
            "",
            "# Ordered project",
            "   @ First action",
            "   @ Second action",
            "",
            "# Another ordered project",
            "  @ Completed first action (DONE 2013-07-20 15:00)",
            "  @ Newly-next Action",
            "  - Fully blocked project",
            "    @ Action A",
            "    @ Action B",
            "    @ Action C",
        ])
        self.trusted_system.SetContexts(include=['test'])
        self.assertItemsEqual(
            ['First action', 'Newly-next Action'],
            [x.text for x in self.trusted_system.NextActions()])

    def testDoneProjectPruned(self):
        self.addAnonymousFile([
            "- @@Test project",
            "  - First subproject (DONE 2013-07-20 15:30)",
            "    @ A task for the first subproject",
            "    @ Another such task",
            "  - Second subproject",
            "    @ A task for the second subproject (DONE 2013-07-20 12:00)",
            "    @ Another second-subproject task",
            "  - Third subproject (WONTDO)",
            "    @ Something urgent but not important",
        ])
        self.trusted_system.SetContexts(include=['test'])
        self.assertItemsEqual(
            ['Another second-subproject task'],
            [x.text for x in self.trusted_system.NextActions()])


class TestTrustedSystemParanoia(TestTrustedSystemBaseClass):
    """Test "paranoia" features.

    All the little things that might cause you to lose trust in the system.
    """

    def testProjectsWithoutNextActions(self):
        """A list of projects which lack Next Actions.

        PROBLEM: Checking off a Next Action which lacks a successor could
            needlessly block a project.
        SOLUTION: List projects without next actions.
        """
        self.addAnonymousFile([
            "# Ordered project.",
            "  @ First task (DONE 2013-05-02 20:59)",
            "",
            "# Another ordered project",
            "  @ First task (DONE 2013-05-02 20:59)",
            "  @ Second task, which makes the parent Project not show up.",
            "",
            "- Empty super-project.",
            "  * The super-project shouldn't show up; the sub-project will.",
            "  - Empty project.",
            "",
            "# Project WITH next action",
            "  @ Next action",
        ])
        projects = self.trusted_system.ProjectsWithoutNextActions()
        self.assertEqual(2, len(projects))
        self.assertItemsEqual(['Ordered project.', 'Empty project.'],
                              [x.text for x in projects])

    def testNextActionsWithoutContexts(self):
        """All next actions which lack a context.

        PROBLEM: It's easy to forget to add a context to a new Next Action, so
            it won't show up in any lists!
        SOLUTION: List next actions without contexts.
        """
        self.addAnonymousFile([
            "# Project with context @test",
            "  @ Should not show up",
            "",
            "# Project without context.",
            "  @ Should show up",
            "",
            "= Section with context @test =",
            "",
            "# Project with implicit context.",
            "  @ Also should not show up",
        ])
        next_actions = self.trusted_system.NextActionsWithoutContexts()
        self.assertEqual(1, len(next_actions))
        self.assertItemsEqual(['Should show up'],
                              [x.text for x in next_actions])
