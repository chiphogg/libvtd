import copy
import datetime
import unittest

from test import libvtd_test

import libvtd.node

from third_party import six


class TestNode(unittest.TestCase):
    """Test various "node" types (Project, Next Action, Comment, etc.)"""

    def testParsingDueDates(self):
        """ Check that valid due dates get parsed, and invalid ones remain."""
        n = libvtd.node.NextAction()
        n.AbsorbText('Test VTD <2013-06-31 <2013-06-29 18:59')

        # The invalid date June 31 should remain in the text.
        self.assertEqual('Test VTD <2013-06-31', n.text)

        # The valid datetime should have been parsed as the due date.
        self.assertEqual(datetime.datetime(2013, 6, 29, 18, 59), n.due_date)

    def testNestingUnderFile(self):
        """Check that any non-File Node can be nested under a File."""
        f = libvtd.node.File()
        self.assertFalse(f.AddChild(libvtd.node.File()))
        self.assertTrue(f.AddChild(libvtd.node.Section()))
        self.assertTrue(f.AddChild(libvtd.node.Project()))
        self.assertTrue(f.AddChild(libvtd.node.NextAction()))
        self.assertTrue(f.AddChild(libvtd.node.Comment()))

    def testNestingUnderSection(self):
        """Check that any non-File node can be nested under a Section."""
        s = libvtd.node.Section()

        # File can never nest under Section.
        self.assertFalse(s.AddChild(libvtd.node.File()))

        # Section can only be added if it's of a higher level.
        self.assertFalse(s.AddChild(libvtd.node.Section(level=s.level)))
        self.assertTrue(s.AddChild(libvtd.node.Section(level=s.level + 1)))

        # Project, NextAction, or Comment can always be added.
        self.assertTrue(s.AddChild(libvtd.node.Project()))
        self.assertTrue(s.AddChild(libvtd.node.NextAction()))
        self.assertTrue(s.AddChild(libvtd.node.Comment()))

    def testNestingUnderProject(self):
        """Check that anything except File or Section can nest under a Project.

        Also check that only sufficiently indented blocks can nest.
        """
        p = libvtd.node.Project()

        # File and Section can never nest under Project.
        self.assertFalse(p.AddChild(libvtd.node.File()))
        self.assertFalse(p.AddChild(libvtd.node.Section()))

        # Project can be added, but only if sufficiently indented.
        self.assertFalse(p.AddChild(libvtd.node.Project(indent=p.indent)))
        self.assertTrue(p.AddChild(libvtd.node.Project(indent=p.indent + 2)))

        # NextAction can be added, but only if sufficiently indented.
        self.assertFalse(p.AddChild(
            libvtd.node.NextAction(indent=p.indent)))
        self.assertTrue(p.AddChild(
            libvtd.node.NextAction(indent=p.indent + 2)))

        # Comment can be added, but only if sufficiently indented.
        self.assertFalse(p.AddChild(libvtd.node.Comment(indent=p.indent)))
        self.assertTrue(p.AddChild(libvtd.node.Comment(indent=p.indent + 2)))

    def testNestingUnderNextAction(self):
        """Check that only Comment can nest under a NextAction."""
        n = libvtd.node.NextAction()

        # File and Section can never nest under Project.
        self.assertFalse(n.AddChild(libvtd.node.File()))
        self.assertFalse(n.AddChild(libvtd.node.Section()))

        # Project cannot be added, regardless of indentation.
        self.assertFalse(n.AddChild(libvtd.node.Project(indent=n.indent)))
        self.assertFalse(n.AddChild(libvtd.node.Project(indent=n.indent + 2)))

        # NextAction cannot be added, regardless of indentation.
        self.assertFalse(n.AddChild(
            libvtd.node.NextAction(indent=n.indent)))
        self.assertFalse(n.AddChild(
            libvtd.node.NextAction(indent=n.indent + 2)))

        # Comment can be added, but only if sufficiently indented.
        self.assertFalse(n.AddChild(libvtd.node.Comment(indent=n.indent)))
        self.assertTrue(n.AddChild(libvtd.node.Comment(indent=n.indent + 2)))

    def testNestingUnderComment(self):
        """Check that only Comment can nest under a Comment."""
        c = libvtd.node.Comment()

        # File and Section can never nest under Project.
        self.assertFalse(c.AddChild(libvtd.node.File()))
        self.assertFalse(c.AddChild(libvtd.node.Section()))

        # Project cannot be added, regardless of indentation.
        self.assertFalse(c.AddChild(libvtd.node.Project(indent=c.indent)))
        self.assertFalse(c.AddChild(libvtd.node.Project(indent=c.indent + 2)))

        # NextAction cannot be added, regardless of indentation.
        self.assertFalse(c.AddChild(
            libvtd.node.NextAction(indent=c.indent)))
        self.assertFalse(c.AddChild(
            libvtd.node.NextAction(indent=c.indent + 2)))

        # Comment can be added, but only if sufficiently indented.
        self.assertFalse(c.AddChild(libvtd.node.Comment(indent=c.indent)))
        self.assertTrue(c.AddChild(libvtd.node.Comment(indent=c.indent + 2)))

    def testAtomicAbsorption(self):
        """Failed call to AbsorbText must leave Node in its original state.
        """
        action = libvtd.node.File.CreateNodeFromLine('  @ Action')
        test_action = copy.deepcopy(action)
        # This text should be invalid, because it's less indented than the
        # parent text.
        self.assertFalse(test_action.AbsorbText('@p:1 @work @t:15 to do'))
        self.maxDiff = None

        # Kind of ugly, but assertDictEqual fails for _diff_functions because
        # the (otherwise identical) functions are bound to different objects.
        keys_to_disregard = ['_diff_functions']
        for key in keys_to_disregard:
            test_action.__dict__.pop(key)
            action.__dict__.pop(key)

        self.assertDictEqual(test_action.__dict__, action.__dict__)

    def testAbsorption(self):
        # File should not ever absorb text; its text should only come from the
        # file contents.
        self.assertFalse(libvtd.node.File(None).AbsorbText('More file text!'))

        # Section should absorb text only when new.
        section = libvtd.node.Section(3)
        self.assertTrue(section.AbsorbText('To do later'))
        self.assertEqual('To do later', section.text)
        self.assertFalse(section.AbsorbText('extra text'))

        # Project can absorb anything indented by enough (and blank lines).
        project = libvtd.node.File.CreateNodeFromLine('  # Project which')
        self.assertTrue(project.AbsorbText(''))
        self.assertFalse(project.AbsorbText('  is NOT indented enough'))
        self.assertTrue(project.AbsorbText('    IS indented enough'))
        self.assertEqual('Project which\n\nIS indented enough', project.text)

        # NextAction can also absorb anything indented by enough.
        action = libvtd.node.File.CreateNodeFromLine('  @ NextAction which')
        self.assertTrue(action.AbsorbText(''))
        self.assertFalse(action.AbsorbText('  is NOT indented enough'))
        self.assertTrue(action.AbsorbText('    IS indented enough'))
        self.assertEqual('NextAction which\n\nIS indented enough', action.text)

        # Comment can also absorb anything indented by enough.
        comment = libvtd.node.File.CreateNodeFromLine('  * Comment which')
        self.assertTrue(comment.AbsorbText(''))
        self.assertFalse(comment.AbsorbText('  is NOT indented enough'))
        self.assertTrue(comment.AbsorbText('    IS indented enough'))
        self.assertEqual('Comment which\n\nIS indented enough', comment.text)

    def testDateStatesNoDates(self):
        """Test DateStates for node with no dates."""
        action = libvtd.node.NextAction()
        self.assertEqual(libvtd.node.DateStates.ready,
                         action.DateState(datetime.datetime.now()))

    def testDateStatesDefaultReadyDate(self):
        """Test DateStates for node with due date, and implicit ready date."""
        action = libvtd.node.NextAction()
        self.assertTrue(action.AbsorbText(
            '@ test default ready date <2013-08-27'))
        # Tasks are 'ready' (i.e., not yet 'due') until the end of the day on
        # the ready date.  The default ready date is 1 day before the due date.
        self.assertEqual(libvtd.node.DateStates.ready,
                         action.DateState(datetime.datetime(2013, 8, 26, 23)))
        # Tasks become due as soon as the ready date ends, and stay due until
        # the end of the day on the due date.
        self.assertEqual(libvtd.node.DateStates.due,
                         action.DateState(datetime.datetime(2013, 8, 27, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         action.DateState(datetime.datetime(2013, 8, 27, 23)))
        # Anything after the due date is late.
        self.assertEqual(libvtd.node.DateStates.late,
                         action.DateState(datetime.datetime(2013, 8, 28, 1)))

    def testDateStatesExplicitReadyDate(self):
        """Test DateStates with explicit ready date."""
        action = libvtd.node.NextAction()
        self.assertTrue(action.AbsorbText(
            '@ test explicit ready date <2013-08-27(2)'))
        # Tasks stay ready until the end of the day on the ready date.
        self.assertEqual(libvtd.node.DateStates.ready,
                         action.DateState(datetime.datetime(2013, 8, 25, 23)))
        # Tasks become due as soon as the ready date begins, and stay due until
        # the end of the day on the due date.
        self.assertEqual(libvtd.node.DateStates.due,
                         action.DateState(datetime.datetime(2013, 8, 26, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         action.DateState(datetime.datetime(2013, 8, 27, 23)))
        # Anything after the due date is late.
        self.assertEqual(libvtd.node.DateStates.late,
                         action.DateState(datetime.datetime(2013, 8, 28, 1)))

    def testDateStatesVisibleDate(self):
        """Test DateStates with explicit ready date."""
        action = libvtd.node.NextAction()
        self.assertTrue(action.AbsorbText('@ test visible date >2013-08-20'))
        # Anything before the visible date is invisible.
        self.assertEqual(libvtd.node.DateStates.invisible,
                         action.DateState(datetime.datetime(2013, 8, 19, 23)))
        # Tasks become ready as soon as the visible date begins.
        self.assertEqual(libvtd.node.DateStates.ready,
                         action.DateState(datetime.datetime(2013, 8, 20, 1)))


class TestFile(unittest.TestCase):
    """Test the File class."""

    def testParseSimpleSection(self):
        """Parse a line corresponding to a section"""
        section = libvtd.node.File.CreateNodeFromLine('= A section =')
        self.assertEqual('A section', section.text)
        self.assertEqual(1, section.level)

    def testParseSectionWithAttributes(self):
        """Parse a section with default priority and contexts."""
        section = libvtd.node.File.CreateNodeFromLine(
            '== @@Home @p:3 relaxing @t:20 ==')
        # The time-tag does *not* get filtered out, because that only works for
        # NextAction objects.
        self.assertEqual('Home relaxing @t:20', section.text)
        self.assertEqual(2, section.level)
        six.assertCountEqual(self, ['home'], section.contexts)
        self.assertEqual(3, section.priority)

    def testParseNextAction(self):
        action = libvtd.node.File.CreateNodeFromLine(
            '  @ @p:1 @@Read @t:15 chapter 8 >2013-06-28 13:00 '
            '@home <2013-07-05 22:30')
        self.assertEqual('NextAction', action.__class__.__name__)
        self.assertEqual('Read chapter 8', action.text)
        six.assertCountEqual(self, ['read', 'home'], action.contexts)
        self.assertEqual(datetime.datetime(2013, 6, 28, 13),
                         action.visible_date)
        self.assertEqual(datetime.datetime(2013, 7, 5, 22, 30),
                         action.due_date)
        self.assertEqual(2, action.indent)
        self.assertEqual(1, action.priority)
        self.assertEqual(15, action.minutes)

    def testFileLineNumbers(self):
        with libvtd_test.TempInput([
            '= Section =',
            '',
            '# Project',
            '  @ Action',
        ]) as file_name:
            file = libvtd.node.File(file_name)
            self.assertTupleEqual((file_name, 1), file.Source())

            section = file.children[0]
            self.assertTupleEqual((file_name, 1), section.Source())

            project = section.children[0]
            self.assertTupleEqual((file_name, 3), project.Source())

            action = project.children[0]
            self.assertTupleEqual((file_name, 4), action.Source())


class TestRecurringActions(unittest.TestCase):
    """Test various kinds of recurring actions."""

    def testDayRecurSimple(self):
        """Test a simple action which recurs every day."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText("Check today's calendar EVERY day"))
        self.assertEqual("Check today's calendar", recur.text)
        self.assertTrue(recur.recurring)
        self.assertEqual(libvtd.node.DateStates.new,
                         recur.DateState(datetime.datetime.now()))

        # After it's been done at least once, its visible, due, and late dates
        # should be set accordingly.
        self.assertTrue(recur.AbsorbText("  (LASTDONE 2013-09-01 16:14)"))
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 1, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 2, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 2, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 3, 1)))

    def testDayRecurDifferentEndTime(self):
        """Test action which recurs every day, where 'days' begin at 9am."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            "Pick out clothes EVERY day [9:00] (LASTDONE 2013-09-01 08:30)"))
        self.assertEqual("Pick out clothes", recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 1, 8, 59)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 1, 9, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 2, 8, 59)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 2, 9, 1)))

    def testDayRecurDifferentStartAndEndTime(self):
        """Test action which recurs every day from 5pm to 9am."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            "Pick out clothes EVERY day [17:00 - 9:00] " +
            "(LASTDONE 2013-09-01 08:30)"))
        self.assertEqual("Pick out clothes", recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 1, 16)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 1, 18)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 2, 8)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 2, 10)))

    def testDayRecurMultipleDays(self):
        """Test action which occurs every 3 days."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Shave EVERY 3 days (LASTDONE 2013-09-01 08:30)'))
        self.assertEqual('Shave', recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 3, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 4, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 4, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 5, 1)))

    def testDayRecurRange(self):
        """Test action which recurs within a given range of days."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Check spare TP in bathrooms EVERY 3-5 days ' +
            '(LASTDONE 2013-09-01 08:30)'))
        self.assertEqual('Check spare TP in bathrooms', recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 3, 23)))
        self.assertEqual(libvtd.node.DateStates.ready,
                         recur.DateState(datetime.datetime(2013, 9, 4, 1)))
        self.assertEqual(libvtd.node.DateStates.ready,
                         recur.DateState(datetime.datetime(2013, 9, 5, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 6, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 6, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 7, 1)))

    def testWeekRecurSimple(self):
        """Test a simple action which recurs every week."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Call parents EVERY week (LASTDONE 2013-09-01 08:30)'))
        self.assertEqual('Call parents', recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 7, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 8, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 14, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 15, 1)))

    def testWeekRecurDueDate(self):
        """Recurs every 1-2 weeks; change boundary so we don't split weekend.

        Also checks that the due date falls on the *end* of the day, if no time
        is specified.
        """
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Call parents EVERY 1-2 weeks[Sun] (LASTDONE 2013-09-03 08:30)'))
        self.assertEqual('Call parents', recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 8, 23)))
        self.assertEqual(libvtd.node.DateStates.ready,
                         recur.DateState(datetime.datetime(2013, 9, 9, 1)))
        self.assertEqual(libvtd.node.DateStates.ready,
                         recur.DateState(datetime.datetime(2013, 9, 15, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 16, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 22, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 23, 1)))

    def testWeekRecurTrickyDateBoundaries(self):
        """Check that visible date is start of day; due date is end of day."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Call parents EVERY 1-2 weeks[Sat - Sun] ' +
            '(LASTDONE 2013-09-03 08:30)'))
        self.assertEqual('Call parents', recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 6, 23)))
        self.assertEqual(libvtd.node.DateStates.ready,
                         recur.DateState(datetime.datetime(2013, 9, 7, 1)))
        self.assertEqual(libvtd.node.DateStates.ready,
                         recur.DateState(datetime.datetime(2013, 9, 8, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 14, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 15, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 16, 1)))

    def testWeekRecurVisibleDate(self):
        """Weekly recurring action with a custom visible date."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Take out garbages EVERY week [Monday 12:00 - Tuesday 7:00] ' +
            '(LASTDONE 2013-09-09 21:30)'))
        self.assertEqual('Take out garbages', recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 16, 11)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 16, 13)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 17, 6)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 17, 8)))

    def testWeekRecurVisibleDateDoneLate(self):
        """
        Actions done late (but before vis-date) should count for previous week.

        Identical to previous test, except it's done late; this shouldn't
        change the due dates at all.
        """
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Take out garbages EVERY week [Monday 12:00 - Tuesday 7:00] ' +
            '(LASTDONE 2013-09-10 07:30)'))
        self.assertEqual('Take out garbages', recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 16, 11)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 16, 13)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 9, 17, 6)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 9, 17, 8)))

    def testMonthRecurSimple(self):
        """Simple task which recurs every month."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Scrub toilets EVERY month (LASTDONE 2013-09-10 07:30)'))
        self.assertEqual('Scrub toilets', recur.text)
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 9, 30, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 10, 1, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 10, 31, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 11, 1, 1)))

    def testMonthRecurTrickyDateBoundaries(self):
        """Check that visible date is start of day; due date is end of day."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Clean out filing cabinets EVERY 4-6 months [4 - 15] ' +
            '(LASTDONE 2013-09-08 21:00)'))
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 1, 3, 23)))
        self.assertEqual(libvtd.node.DateStates.ready,
                         recur.DateState(datetime.datetime(2014, 1, 4, 1)))
        self.assertEqual(libvtd.node.DateStates.ready,
                         recur.DateState(datetime.datetime(2014, 2, 15, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2014, 2, 16, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2014, 3, 15, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2014, 3, 16, 1)))

    def testMonthRecurNegativeDates(self):
        """Negative dates go from the end of the month."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Do budget for new month EVERY month [-3 - 0] ' +
            '(LASTDONE 2014-02-08 22:00)'))
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 2, 24, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2014, 2, 25, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2014, 2, 28, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2014, 3, 1, 1)))

    def testMonthRecurVisibleDueTimes(self):
        """Monthly recurring tasks with due times/visible times."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Do budget for new month EVERY month [-3 8:00 - 0 18:00] ' +
            '(LASTDONE 2014-02-08 22:00)'))
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 2, 25, 7)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2014, 2, 25, 9)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2014, 2, 28, 17)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2014, 2, 28, 19)))

    def testMonthRecurVisibleDateDoneLate(self):
        """Paying the rent late shouldn't skip next month's rent."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            'Pay rent EVERY month [7 - 10] (LASTDONE 2013-09-12 22:00)'))
        self.assertEqual(libvtd.node.DateStates.invisible,
                         recur.DateState(datetime.datetime(2013, 10, 6, 23)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 10, 7, 1)))
        self.assertEqual(libvtd.node.DateStates.due,
                         recur.DateState(datetime.datetime(2013, 10, 10, 23)))
        self.assertEqual(libvtd.node.DateStates.late,
                         recur.DateState(datetime.datetime(2013, 10, 11, 1)))

    def testMonthlyIsDoneIfLastdoneAtStartOfInterval(self):
        """Guards against chiphogg/vim-vtd#17."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            '@ Run EVERY month [1 09:00 - 3] (LASTDONE 2019-09-01 09:00)'))
        self.assertEqual(
                libvtd.node.DateStates.invisible,
                recur.DateState(datetime.datetime(2019, 9, 1, 9, 0)))
        self.assertEqual(
                libvtd.node.DateStates.invisible,
                recur.DateState(datetime.datetime(2019, 10, 1, 8, 59)))
        self.assertEqual(
                libvtd.node.DateStates.due,
                recur.DateState(datetime.datetime(2019, 10, 1, 9, 0)))

    def testWeeklyIsDoneIfLastdoneAtStartOfInterval(self):
        """Guards against chiphogg/vim-vtd#17."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            '@ Run EVERY week [Fri 09:00 - 17:00] (LASTDONE 2015-01-30 09:00)'))
        self.assertEqual(
                libvtd.node.DateStates.invisible,
                recur.DateState(datetime.datetime(2015, 1, 30, 9, 0)))
        self.assertEqual(
                libvtd.node.DateStates.invisible,
                recur.DateState(datetime.datetime(2015, 2, 6, 8, 59)))
        self.assertEqual(
                libvtd.node.DateStates.due,
                recur.DateState(datetime.datetime(2015, 2, 6, 9, 0)))

    def testDailyIsDoneIfLastdoneAtStartOfInterval(self):
        """Guards against chiphogg/vim-vtd#17."""
        recur = libvtd.node.NextAction()
        self.assertTrue(recur.AbsorbText(
            '@ Run EVERY day [09:00 - 17:00] (LASTDONE 2015-01-30 09:00)'))
        self.assertEqual(
                libvtd.node.DateStates.invisible,
                recur.DateState(datetime.datetime(2015, 1, 30, 9, 0)))
        self.assertEqual(
                libvtd.node.DateStates.invisible,
                recur.DateState(datetime.datetime(2015, 1, 31, 8, 59)))
        self.assertEqual(
                libvtd.node.DateStates.due,
                recur.DateState(datetime.datetime(2015, 1, 31, 9, 0)))
