import datetime
import itertools
import os
import subprocess
import tempfile
import unittest

from test import libvtd_test
from third_party import six

import libvtd.node
import libvtd.trusted_system


class TestTrustedSystemBaseClass(unittest.TestCase):

    def setUp(self):
        self.trusted_system = libvtd.trusted_system.TrustedSystem()

    def addAnonymousFile(self, data):
        with libvtd_test.TempInput(data) as file_name:
            self.trusted_system.AddFile(file_name)


class TestTrustedSystemNextActions(TestTrustedSystemBaseClass):
    def testShowAllContextsIfNoneSelected(self):
        self.addAnonymousFile([
            "@ Play with kids @home",
            "@ Do some @@work",
            "@ @@waiting for package",
        ])

        # With no contexts included, we should show all (non-excluded) actions.
        self.trusted_system.SetContexts(exclude=['waiting'])
        next_actions = self.trusted_system.NextActions()
        six.assertCountEqual(
                self,
                ['Play with kids', 'Do some work'],
                [x.text for x in next_actions]) 
        # When we include a context, only show actions from that context.
        self.trusted_system.SetContexts(include=['home'], exclude=['waiting'])
        next_actions = self.trusted_system.NextActions()
        six.assertCountEqual(
                self, ['Play with kids'], [x.text for x in next_actions])

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
            "@ Action which cancels all inheritance @!",
        ])
        # Check @test actions
        self.trusted_system.SetContexts(include=['test'])
        next_actions = self.trusted_system.NextActions()
        six.assertCountEqual(
                self,
                ['Top-level action', 'Inherited action'],
                [x.text for x in next_actions])
        # Check @x actions
        self.trusted_system.SetContexts(include=['x'])
        next_actions = self.trusted_system.NextActions()
        six.assertCountEqual(
                self,
                ["Action which should show up only under 'x'"],
                [x.text for x in next_actions])

        # Test ability to cancel all inheritance with '@!'.
        self.trusted_system.SetContexts(include=[], exclude=['test', 'x'])
        next_actions = self.trusted_system.NextActions()
        six.assertCountEqual(
                self,
                ["Action which cancels all inheritance"],
                [x.text for x in next_actions])

    def testInheritPriority(self):
        self.addAnonymousFile([
            "= Section @p:4 =",
            "",
            "@ Priority 4 task",
            "- Unordered Project @p:2",
            "  @ Priority 2 task",
            "  @ Priority 0 task @p:0",
            "# Ordered project (implicit priority 4)",
            "  @ Do ordered project",
        ])
        next_actions = self.trusted_system.NextActions()
        self.assertEqual(4, len(next_actions))
        self.assertEqual(0, libvtd_test.FirstTextMatch(next_actions,
                                                       "Priority 0").priority)
        self.assertEqual(2, libvtd_test.FirstTextMatch(next_actions,
                                                       "Priority 2").priority)
        self.assertEqual(4, libvtd_test.FirstTextMatch(next_actions,
                                                       "Priority 4").priority)
        self.assertEqual(4, libvtd_test.FirstTextMatch(next_actions,
                                                       "Do ordered").priority)

    def testInheritDueDate(self):
        self.addAnonymousFile([
            "@ No due date",
            "",
            "- Project with due date <2013-08-25",
            "  @ Inherits due date",
            "  @ Has own due date <2013-08-23",
            "  @ Use earliest of all due dates <2013-08-27",
            "",
            "= Section with due date <2013-07-25 =",
            "",
            "@ Get section's due date",
            "",
            "- Project without explicit due date",
            "  @ Multi-level due date inheritance",
        ])
        next_actions = self.trusted_system.NextActions()
        self.assertEqual(6, len(next_actions))
        self.assertIsNone(libvtd_test.FirstTextMatch(next_actions,
                                                     "^No due date$").due_date)
        self.assertEqual(libvtd_test.DueDate("2013-08-25"),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Inherits due").due_date)
        self.assertEqual(libvtd_test.DueDate("2013-08-23"),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Has own due").due_date)
        self.assertEqual(libvtd_test.DueDate("2013-08-25"),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Use earliest").due_date)
        self.assertEqual(libvtd_test.DueDate("2013-07-25"),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Get section").due_date)
        self.assertEqual(libvtd_test.DueDate("2013-07-25"),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Multi-level").due_date)
        # Don't forget to test that the implicit ready_date gets inherited.
        self.assertEqual(libvtd_test.DueDate("2013-07-24"),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Multi-level").ready_date)

    def testInheritVisibleDate(self):
        self.addAnonymousFile([
            "@ No visible date",
            "",
            "- Project with visible date >2013-08-25",
            "  @ Inherits visible date",
            "  @ Has own visible date >2013-08-27",
            "  @ Use latest of all visible dates >2013-08-21",
            "",
            "= Section with visible date >2013-07-25 =",
            "",
            "@ Get section's visible date",
            "",
            "- Project without explicit visible date",
            "  @ Multi-level visible date inheritance",
            "",
            "@ Invisible action >2013-09-05",
        ])
        now = datetime.datetime(2013, 9, 1)
        next_actions = self.trusted_system.NextActions(now=now)
        self.assertEqual(6, len(next_actions))
        self.assertIsNone(libvtd_test.FirstTextMatch(next_actions,
                                                     "^No visib").visible_date)
        self.assertEqual(datetime.datetime(2013, 8, 25),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Inherits ").visible_date)
        self.assertEqual(datetime.datetime(2013, 8, 27),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Has own v").visible_date)
        self.assertEqual(datetime.datetime(2013, 8, 25),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Use lates").visible_date)
        self.assertEqual(datetime.datetime(2013, 7, 25),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Get secti").visible_date)
        self.assertEqual(datetime.datetime(2013, 7, 25),
                         libvtd_test.FirstTextMatch(next_actions,
                                                    "^Multi-lev").visible_date)

    def testIgnoreRecurs(self):
        self.addAnonymousFile([
            "@ Regular action",
            "@ Recurring action",
            "  EVERY day",
        ])
        six.assertCountEqual(
                self, 
                ['Regular action'],
                [x.text for x in self.trusted_system.NextActions()])

    def testExcludeWaiting(self):
        """Actions on the "waiting" list should not be shown."""
        self.addAnonymousFile([
            "# Project",
            "  * Doesn't have a NextAction as such (since it's 'waiting'),",
            "    but shouldn't show up in ProjectsWithoutNextActions().",
            "  @ @@waiting for Godot",
        ])

        self.assertEqual(0, len(self.trusted_system.NextActions()))
        self.assertEqual(0, len(self.trusted_system.ContextList()))
        self.assertEqual(0,
                         len(self.trusted_system.ProjectsWithoutNextActions()))

    def testDone(self):
        self.addAnonymousFile([
            "@ Finished action (DONE)",
            "@ Unfinished action",
        ])
        six.assertCountEqual(
                self, 
                ['Unfinished action'],
                [x.text for x in self.trusted_system.NextActions()])

    def testRefresh(self):
        # First iteration of test file: just one action.
        temp = tempfile.NamedTemporaryFile('w', delete=False)
        temp.write('\n'.join([
            "@ first action"
        ]))
        temp.close()
        self.trusted_system.AddFile(temp.name)
        self.assertLess(os.path.getmtime(temp.name),
                        self.trusted_system.last_refreshed)
        six.assertCountEqual(
                self, 
                ['first action'],
                [x.text for x in self.trusted_system.NextActions()])

        # Add text to the file, but make the system think it's already been
        # updated; this new action should not show up.
        with open(temp.name, 'a') as temp_file:
            temp_file.write('\n@ next action')
        time_interval = 60  # Adjust timestamps by this (arbitrary) amount.
        self.trusted_system.last_refreshed += time_interval
        self.trusted_system.Refresh()
        six.assertCountEqual(
                self, 
                ['first action'],
                [x.text for x in self.trusted_system.NextActions()])

        # Refresh() should update the timestamp and find the new action.
        self.trusted_system.last_refreshed -= 2 * time_interval
        self.trusted_system.Refresh()
        self.assertLess(os.path.getmtime(temp.name),
                        self.trusted_system.last_refreshed)
        six.assertCountEqual(
                self, 
                ['first action', 'next action'],
                [x.text for x in self.trusted_system.NextActions()])

        # Clean up after ourselves.
        os.unlink(temp.name)


class TestTrustedSystemRecurringActions(TestTrustedSystemBaseClass):
    def testRecurs(self):
        self.addAnonymousFile([
            "@ Check calendar EVERY day",
            "  (LASTDONE 2013-09-11 23:04)",  # (Wednesday.)
            "@ Take out garbage EVERY week [Thu 17:00 - Fri 07:00]",
            "  (LASTDONE 2013-09-06 07:10)",  # (Friday.)
            "@ Scrub toilets EVERY 4-6 weeks",
            "  (LASTDONE 2013-08-16 21:00)",  # (Friday.)
            "@ Fix obscure boundary bug EVERY day [09:00]",
            "  (LASTDONE 2013-09-11 09:00)",
        ])
        now = datetime.datetime(2013, 9, 12, 21, 20)  # (Thursday.)
        recurs = self.trusted_system.RecurringActions(now)
        self.assertEqual(4, len(recurs))
        six.assertCountEqual(
                self, 
                [
                    'Check calendar',
                    'Take out garbage',
                    'Scrub toilets',
                    'Fix obscure boundary bug',
                ],
                [x.text for x in recurs])

        recur_1 = libvtd_test.FirstTextMatch(recurs, "^Check calendar$")
        self.assertEqual(datetime.datetime(2013, 9, 13), recur_1.due_date)
        self.assertEqual(libvtd.node.DateStates.due, recur_1.DateState(now))

        recur_2 = libvtd_test.FirstTextMatch(recurs, "^Take out garbage$")
        self.assertEqual(datetime.datetime(2013, 9, 13, 7), recur_2.due_date)
        self.assertEqual(libvtd.node.DateStates.due, recur_2.DateState(now))

        recur_3 = libvtd_test.FirstTextMatch(recurs, "^Scrub toilets$")
        self.assertEqual(datetime.datetime(2013, 9, 29), recur_3.due_date)
        self.assertEqual(libvtd.node.DateStates.ready, recur_3.DateState(now))

        recur_4 = libvtd_test.FirstTextMatch(recurs, "^Fix obscure boundary.*")
        self.assertEqual(datetime.datetime(2013, 9, 13, 9), recur_4.due_date)
        self.assertEqual(libvtd.node.DateStates.due, recur_4.DateState(now))

    def testExcludeInboxes(self):
        """Actions on the "inbox" list should not be shown."""
        self.addAnonymousFile([
            "@ Empty @@home @@inbox EVERY 3-5 days",
        ])
        self.assertEqual(0, len(self.trusted_system.RecurringActions()))

    def testUnorderedRecurringProjects(self):
        """Inherit recurrence information; separate LASTDONE information."""
        self.addAnonymousFile([
            "- Change passwords EVERY 2 months",
            "  @ Google (LASTDONE 2013-11-04 06:00)",
            "  @ Facebook",
            "  @ Bank (LASTDONE 2013-10-28 11:00)",
        ])
        now = datetime.datetime(2014, 1, 3)
        recurs = self.trusted_system.RecurringActions(now)
        self.assertEqual(3, len(recurs))
        six.assertCountEqual(
                self, ['Google', 'Facebook', 'Bank'], [x.text for x in recurs])

        recur_1 = libvtd_test.FirstTextMatch(recurs, "^Google$")
        self.assertEqual(libvtd.node.DateStates.due, recur_1.DateState(now))

        recur_2 = libvtd_test.FirstTextMatch(recurs, "^Facebook$")
        self.assertEqual(libvtd.node.DateStates.new, recur_2.DateState(now))

        recur_3 = libvtd_test.FirstTextMatch(recurs, "^Bank$")
        self.assertEqual(libvtd.node.DateStates.late, recur_3.DateState(now))


class TestTrustedSystemWaiting(TestTrustedSystemBaseClass):
    def testWaiting(self):
        """'Waiting' items appear in Waiting()."""
        self.addAnonymousFile([
            "@ @@Waiting for Godot",
            "@ Get code review @waiting <2013-10-10(30)",
            "@ @waiting Good GTD system in vim",
            "  (DONE 2013-10-01 01:23)",
            "@ Invisible @@waiting item >2013-10-10"
        ])
        now = datetime.datetime(2013, 10, 1, 9, 40)
        waiting = self.trusted_system.Waiting(now)

        self.assertEqual(2, len(waiting))
        six.assertCountEqual(
                self,
                ['Waiting for Godot', 'Get code review'],
                [x.text for x in waiting])

        waiting_2 = libvtd_test.FirstTextMatch(waiting, "^Get code review$")
        self.assertEqual(libvtd.node.DateStates.due, waiting_2.DateState(now))


class TestTrustedSystemInboxes(TestTrustedSystemBaseClass):
    def testInboxes(self):
        """'Inbox' items appear in Inboxes()."""
        self.addAnonymousFile([
            "@ @@home @@inbox EVERY 3-5 days",
            "@ Google Keep @@inbox EVERY day",
            "  (LASTDONE 2013-09-11 09:30)",
            "@ Email @@inbox EVERY 2-3 days",
            "  (LASTDONE 2013-09-11 09:40)",
            "@ @@work @@inbox EVERY 3-7 days",
        ])
        now = datetime.datetime(2013, 9, 12, 9, 40)
        self.trusted_system.SetContexts(exclude=['work'])
        inboxes = self.trusted_system.Inboxes(now)
        self.assertEqual(2, len(inboxes))
        six.assertCountEqual(
                self,
                ['home inbox', 'Google Keep inbox'],
                [x.text for x in inboxes])

        inbox_1 = libvtd_test.FirstTextMatch(inboxes, '^home inbox$')
        self.assertEqual(libvtd.node.DateStates.new, inbox_1.DateState(now))

        inbox_2 = libvtd_test.FirstTextMatch(inboxes, '^Google Keep inbox$')
        self.assertEqual(libvtd.node.DateStates.due, inbox_2.DateState(now))


class TestTrustedSystemAll(TestTrustedSystemBaseClass):
    def testAll(self):
        """'All' combines NextActions, Inboxes, and RecurringActions."""
        self.addAnonymousFile([
            "@ @@home @@inbox EVERY 3-5 days",
            "@ Check calendar EVERY day",
            "@ Walk the dog",
            "@ @@Waiting for Godot",
        ])
        now = datetime.datetime(2013, 9, 12, 9, 40)
        all = self.trusted_system.AllActions(now)
        self.assertEqual(3, len(all))
        six.assertCountEqual(
                self,
                ['home inbox', 'Check calendar', 'Walk the dog'],
                [x.text for x in all])

    def testAllIncludesMissingNextActions(self):
        self.addAnonymousFile(["# Ordered project"])
        all = self.trusted_system.AllActions()
        six.assertCountEqual(
                self, ['{MISSING Next Action}'], [x.text for x in all])


class TestTrustedSystemContexts(TestTrustedSystemBaseClass):
    def testListContexts(self):
        self.addAnonymousFile([
            "@ E.T. @@phone @@home",                # home, phone
            "@ Go @@home",                          # home
            "@ @@Waiting for a @@phone call",       # Don't include waiting
            "@ @@Work harder EVERY day",            # work
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
        actual_contexts = self.trusted_system.ContextList()
        six.assertCountEqual(self, expected_contexts, actual_contexts)

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
        six.assertCountEqual(
                self, 
                ['Phone mom', 'Pay rent', 'Fix bug: colons', 'Fix SEGV bug!!'],
                [x.text for x in self.trusted_system.NextActions()])


class TestTrustedSystemPatches(TestTrustedSystemBaseClass):
    """Nodes should return a patch to perform various actions."""
    def testPatchMarkAsDone(self):
        """Mark a NextAction as DONE."""
        with libvtd_test.TempInput(['@ test patches', '']) as file_name:
            self.trusted_system.AddFile(file_name)
            six.assertCountEqual(
                    self, 
                    ['test patches'],
                    [x.text for x in self.trusted_system.NextActions()])
            action = libvtd_test.FirstTextMatch(
                self.trusted_system.NextActions(), "^test")

            with open('/dev/null', 'w') as DEVNULL:
                # Get and apply the patch to check this off as DONE.
                patch = action.Patch(libvtd.node.Actions.MarkDONE)
                subprocess.Popen(
                        'patch {}'.format(action.file_name),
                        shell=True,
                        stdout=DEVNULL,
                        stdin=subprocess.PIPE,
                        ).communicate(patch.encode())
                self.trusted_system.Refresh(force=True)
                six.assertCountEqual(
                        self,
                        [],
                        self.trusted_system.NextActions())

                # Apply the patch in reverse; the action should reappear.
                subprocess.Popen(
                        'patch -R {}'.format(action.file_name),
                        shell=True,
                        stdout=DEVNULL,
                        stdin=subprocess.PIPE,
                        ).communicate(patch.encode())
                self.trusted_system.Refresh(force=True)
                six.assertCountEqual(
                        self, 
                        ['test patches'],
                        [x.text for x in self.trusted_system.NextActions()])

    def testPatchRecurUpdateLastdone(self):
        """Update a recurring action's LASTDONE timestamp."""
        with libvtd_test.TempInput([
            '@ New recurring',
            '  action EVERY day',
            '@ Old recurring action EVERY week (LASTDONE 2013-09-01 22:00)',
            '',
        ]) as file_name:
            self.trusted_system.AddFile(file_name)
            now = datetime.datetime(2013, 9, 10, 8)
            recurs = self.trusted_system.RecurringActions(now)
            six.assertCountEqual(
                    self, 
                    ['New recurring\naction', 'Old recurring action'],
                    [x.text for x in recurs])
            recur1 = libvtd_test.FirstTextMatch(recurs, "^New recurring\nacti")
            recur2 = libvtd_test.FirstTextMatch(recurs, "^Old recurring actio")
            self.assertEqual(libvtd.node.DateStates.new, recur1.DateState(now))
            self.assertEqual(libvtd.node.DateStates.due, recur2.DateState(now))

            # Check off both actions and make sure they're no longer visible.
            for recur in [recur1, recur2]:
                self.trusted_system.Refresh(force=True)
                patch = recur.Patch(libvtd.node.Actions.UpdateLASTDONE, now)
                p = subprocess.Popen('patch {}'.format(file_name),
                                     shell=True,
                                     stdin=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     stdout=subprocess.PIPE)
                p.communicate(patch.encode())
            self.trusted_system.Refresh(force=True)
            six.assertCountEqual(
                    self,
                    [],
                    [x.text for x in self.trusted_system.RecurringActions(now)])

            # Check that both are visible one week later.
            now = datetime.datetime(2013, 9, 17)
            recurs = self.trusted_system.RecurringActions(now)
            six.assertCountEqual(
                    self, 
                    ['New recurring\naction', 'Old recurring action'],
                    [x.text for x in recurs])
            recur1 = libvtd_test.FirstTextMatch(recurs, "^New recurring\nacti")
            recur2 = libvtd_test.FirstTextMatch(recurs, "^Old recurring actio")
            self.assertEqual(libvtd.node.DateStates.late,
                             recur1.DateState(now))
            self.assertEqual(libvtd.node.DateStates.due, recur2.DateState(now))

    def testPatchNextActionUpdateLastdoneIgnoresNonRecurring(self):
        """Non-recurring actions get ignored by UpdateLASTDONE patches."""
        with libvtd_test.TempInput(['@ One-time action']) as file_name:
            self.trusted_system.AddFile(file_name)
            actions = self.trusted_system.NextActions()
            self.assertEqual(1, len(actions))
            action = actions[0]
            self.assertFalse(action.recurring)
            self.assertEqual('',
                             action.Patch(libvtd.node.Actions.UpdateLASTDONE))

    def testPatchDefaultCheckoff(self):
        """Mark non-recurring actions as DONE; update LASTDONE if recurring."""
        now = datetime.datetime(2013, 10, 31, 17, 30)
        with libvtd_test.TempInput([
            '@ One-time action',
            '@ Do this EVERY day',
        ]) as file_name:
            self.trusted_system.AddFile(file_name)

            # Non-recurring action should be marked DONE.
            actions = self.trusted_system.NextActions()
            self.assertEqual(1, len(actions))
            self.assertFalse(actions[0].recurring)
            six.assertRegex(
                    self,
                    actions[0].Patch(libvtd.node.Actions.DefaultCheckoff, now),
                    r'\(DONE 2013-10-31 17:30\)')

            # Recurring action should get its LASTDONE timestamp updated.
            actions = self.trusted_system.RecurringActions()
            self.assertEqual(1, len(actions))
            self.assertTrue(actions[0].recurring)
            six.assertRegex(
                    self, 
                    actions[0].Patch(libvtd.node.Actions.DefaultCheckoff, now),
                    r'\(LASTDONE 2013-10-31 17:30\)')


class TestTrustedSystemProjects(TestTrustedSystemBaseClass):
    def testExplicitBlockers(self):
        self.addAnonymousFile([
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
        six.assertCountEqual(
                self, 
                ['First action', 'Newly unblocked action', 'Blocker nonexistent'],
                [x.text for x in self.trusted_system.NextActions()])

    def testOrderedProjects(self):
        self.addAnonymousFile([
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
        six.assertCountEqual(
                self, 
                ['First action', 'Newly-next Action'],
                [x.text for x in self.trusted_system.NextActions()])

    def testDoneProjectPruned(self):
        self.addAnonymousFile([
            "- Test project",
            "  - First subproject (DONE 2013-07-20 15:30)",
            "    @ A task for the first subproject",
            "    @ Another such task",
            "  - Second subproject",
            "    @ A task for the second subproject (DONE 2013-07-20 12:00)",
            "    @ Another second-subproject task",
            "  - Third subproject (WONTDO)",
            "    @ Something urgent but not important",
        ])
        six.assertCountEqual(
                self, 
                ['Another second-subproject task'],
                [x.text for x in self.trusted_system.NextActions()])

    def testStubForProjectsWithoutNextActions(self):
        """Project without NextAction should prompt user."""
        self.addAnonymousFile([
            "- Project having subprojects @p:1",
            "  # First subproject has an action",
            "    @ (Here it is!)",
            "  - Second subproject no longer has an action",
            "    @ Old action (DONE)",
            "",
            "- Project to @@ignore even though it lacks NextActions",
            "",
            "# Test that blocked projects don't get stubs",
            "  @ First action",
            "  # Subproject",
        ])
        self.trusted_system.SetContexts(exclude=['ignore'])
        next_actions = self.trusted_system.NextActions()
        six.assertCountEqual(
                self, 
                ['(Here it is!)', '{MISSING Next Action}', 'First action'],
                [x.text for x in next_actions])

        # Checking off the stub should really check off its parent.
        stub = libvtd_test.FirstTextMatch(next_actions, "MISSING")
        self.assertEqual('Second subproject no longer has an action',
                         stub.parent.text)
        self.assertTupleEqual(stub.Source(), stub.parent.Source())
        self.assertEqual(stub.Patch(libvtd.node.Actions.MarkDONE),
                         stub.parent.Patch(libvtd.node.Actions.MarkDONE))
        self.assertEqual(stub.Patch(libvtd.node.Actions.DefaultCheckoff),
                         stub.parent.Patch(
                             libvtd.node.Actions.DefaultCheckoff))


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
            "",
            "# Project which is (DONE)",
        ])
        projects = self.trusted_system.ProjectsWithoutNextActions()
        self.assertEqual(2, len(projects))
        six.assertCountEqual(
                self,
                ['Ordered project.', 'Empty project.'],
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
            "= Section with context @foo =",
            "",
            "# Project with implicit context.",
            "  @ Also should not show up",
        ])
        next_actions = self.trusted_system.NextActionsWithoutContexts()
        self.assertEqual(1, len(next_actions))
        six.assertCountEqual(
                self, ['Should show up'], [x.text for x in next_actions])
