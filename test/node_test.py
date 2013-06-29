import unittest

import libvtd.node


class TestNodeNesting(unittest.TestCase):
    """Test various "node" types (Project, Next Action, Comment, etc.)"""

    def setUp(self):
        self.section = libvtd.node.Section()
        self.project = libvtd.node.Project()
        self.next_action = libvtd.node.NextAction()
        self.comment = libvtd.node.Comment()

    def testSanityOfReferences(self):
        """Not sure how variables and objects in python work.

        Try getting at a variable by changing its child's parent.
        """
        self.assertTrue(self.project.AddChild(self.next_action))
        test_string = 'Just some random string'
        self.project.children[0].parent.text = test_string
        self.assertTrue(self.project.text == test_string)

    def testNestingUnderSection(self):
        """Check that any type of node can be nested under a Section."""
        self.assertTrue(self.section.AddChild(libvtd.node.Section()))
        self.assertTrue(self.section.AddChild(self.project))
        self.assertTrue(self.section.AddChild(self.next_action))
        self.assertTrue(self.section.AddChild(self.comment))

    def testNestingUnderProject(self):
        """Check that anything except Section can nest under a Project."""
        self.assertFalse(self.project.AddChild(self.section))
        self.assertTrue(self.project.AddChild(libvtd.node.Project()))
        self.assertTrue(self.project.AddChild(self.next_action))
        self.assertTrue(self.project.AddChild(self.comment))

    def testNestingUnderNextAction(self):
        """Check that only Comment can nest under a NextAction."""
        self.assertFalse(self.next_action.AddChild(self.section))
        self.assertFalse(self.next_action.AddChild(self.project))
        self.assertFalse(self.next_action.AddChild(libvtd.node.NextAction()))
        self.assertTrue(self.next_action.AddChild(self.comment))

    def testNestingUnderComment(self):
        """Check that only Comment can nest under a Comment."""
        self.assertFalse(self.comment.AddChild(self.section))
        self.assertFalse(self.comment.AddChild(self.project))
        self.assertFalse(self.comment.AddChild(self.next_action))
        self.assertTrue(self.comment.AddChild(libvtd.node.Comment()))
