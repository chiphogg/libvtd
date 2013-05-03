import contextlib
import os
import re
import tempfile
import unittest

################################################################################
# Helper functions

@contextlib.contextmanager
def TempInput(data):
    temp = tempfile.NamedTemporaryFile(delete=False)
    temp.write(data)
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

################################################################################
# Test code

class TestTrustedSystemBaseClass(unittest.TestCase):

    def setUp(self):
        self.trusted_system = TrustedSystem()

    def addAnonymousFile(self, data):
        with TempInput(data) as file_name:
            self.trusted_system.AddFile(file_name)

class TestTrustedSystemNextActions(TestTrustedSystemBaseClass):
    def testInheritContext(self):
        self.addAnonymousFile(
                "@test"
                ""
                "@ Top-level action"
                "- Project"
                "  @ Inherited action"
                "- Project which cancels context @!test @x"
                "  @ Action which should show up only under 'x'"
                )
        # Check @test actions
        next_actions = self.trusted_system.NextActions(contexts = ['test'])
        self.assertItemsEqual(['Top-level action', 'Inherited action'],
                              [x.text for x in next_actions])
        # Check @x actions
        next_actions = self.trusted_system.NextActions(contexts = ['x'])
        self.assertItemsEqual(["Action which should show up only under 'x'"],
                              [x.text for x in next_actions])
        # Get the actions; check their priorities... somehow!

    def testInheritPriority(self):
        self.addAnonymousFile(
                "@p:4 @test"
                ""
                "@ Priority 4 task"
                "- Unordered Project @p:2"
                "  @ Priority 2 task"
                "  @ Priority 0 task @p:0"
                )
        next_actions = self.trusted_system.NextActions(contexts = ['test'])
        self.assertEqual(3, len(next_actions))
        self.assertEqual(0, FirstTextMatch(next_actions, "Priority 0").priority)
        self.assertEqual(2, FirstTextMatch(next_actions, "Priority 2").priority)
        self.assertEqual(4, FirstTextMatch(next_actions, "Priority 4").priority)
        # Get the actions; check their priorities... somehow!

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
        self.addAnonymousFile(
            "# Ordered project."
            "  @ First task (DONE 2013-05-02 20:59)"
            ""
            "- Empty project."
            ""
            "# Project WITH next action"
            "  @ Next action"
            )
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
        self.addAnonymousFile(
            "# Project with context @test."
            "  @ Should not show up"
            ""
            "# Project without context."
            "  @ Should show up"
            ""
            "= Section with context ="
            "@test"
            ""
            "# Project with implicit context."
            "  @ Also should not show up"
            next_actions = self.trusted_system.NextActionsWithoutContexts()
            self.assertEqual(1, len(next_actions))
            self.assertItemsEqual(['Should show up'],
                                  [x.text for x in next_actions])





