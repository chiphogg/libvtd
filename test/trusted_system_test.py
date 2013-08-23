import contextlib
import itertools
import os
import re
import tempfile
import unittest

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
        ])
        self.trusted_system.SetContexts(include=['test'])
        next_actions = self.trusted_system.NextActions()
        self.assertEqual(3, len(next_actions))
        self.assertEqual(0, FirstTextMatch(next_actions, "Pri.*0").priority)
        self.assertEqual(2, FirstTextMatch(next_actions, "Pri.*2").priority)
        self.assertEqual(4, FirstTextMatch(next_actions, "Pri.*4").priority)

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
