import collections
import datetime
import os

import libvtd.node


class TrustedSystem:
    """A system to keep track of all projects and actions."""

    def __init__(self):
        self._files = {}
        self._contexts_to_include = []
        self._contexts_to_exclude = []

    def AddFile(self, file_name):
        """Read and parse contents of file_name, adding to system.

        Also Refresh()es all existing files, to avoid having some files
        up-to-date and others not.

        Args:
            file_name: The name of a file to read.
        """
        self.Refresh()
        self._files[file_name] = libvtd.node.File(file_name)

    def Refresh(self, force=False):
        """Reread any files updated since the last Refresh()."""
        for file_name in self._files.keys():
            if force or os.path.getmtime(file_name) > self.last_refreshed:
                self._files[file_name] = libvtd.node.File(file_name)
        self.last_refreshed = float(datetime.datetime.now().strftime('%s.%f'))

    def Collect(self, node, matcher,
                pruner=lambda x: 'done' in x.__dict__ and x.done):
        """Gather Nodes from node and its children which fulfil some criteria.

        Args:
            node: A Node object (presumably from within a tree in the
                TrustedSystem).
            matcher: A function which decides whether node should be added to
                the collection.
            pruner: A function which decides whether node's children should be
                explored; defaults to no pruning.

        Returns:
            A sequence of Node objects, from node and its children, which
            match.
        """
        if not node:
            return []
        match_list = [node] if matcher(node) else []
        if not pruner(node):
            for child in node.children:
                match_list.extend(self.Collect(child, matcher=matcher,
                                               pruner=pruner))
        return match_list

    def ContextList(self, now=None):
        """All contexts with visible NextActions, together with a count.

        Returns:
            A list of (context, count) pairs, ordered first by the count
            (descending) and second by the context (alphabetical).
        """
        contexts = collections.Counter()

        if not now:
            now = datetime.datetime.now()

        def Matcher(node):
            if self._VisibleNextAction(node, now):
                contexts.update(node.contexts)
            return False

        for file in self._files.values():
            self.Collect(node=file, matcher=Matcher)

        return contexts.most_common()

    def FindFirstNode(self, node, matcher):
        """Find Node N where matcher(N) is True, from node and its children.

        Args:
            node: A Node object to search.
            matcher: A function accepting a Node which defines what we're
                looking for.

        Returns:
            The first Node to match.
        """
        if matcher(node):
            return node
        for child in node.children:
            match = self.FindFirstNode(child, matcher)
            if match:
                return match
        return None

    def _VisibleNextAction(self, node, now):
        """Check whether node is a NextAction which is currently visible.

        (Does not check contexts.)

        Args:
            node: The object to check.

        Returns:
            Boolean indicating whether this is a currently-visible (i.e., apart
            from contexts) NextAction.
        """
        return self._VisibleAction(node, now) and not (node.recurring or
                                                       node.waiting)

    def _VisibleAction(self, node, now):
        """Check: node is a currently visible Next or Recurring Action.

        (Does not check contexts.)

        Args:
            node: The object to check.

        Returns:
            Boolean indicating whether this is a currently-visible (i.e., apart
            from contexts) NextAction.
        """
        return (isinstance(node, libvtd.node.NextAction)
                and node.DateState(now) != libvtd.node.DateStates.invisible
                and not self._Blocked(node)
                and not node.done)

    def _VisibleRecurringAction(self, node, now):
        """Check whether node is a Recurring Action which is currently visible.

        (Does not check contexts.)

        Args:
            node: The object to check.

        Returns:
            Boolean indicating whether this is a currently-visible (i.e., apart
            from contexts) NextAction.
        """
        return self._VisibleAction(node, now) and (node.recurring and not
                                                   node.inbox)

    def NextActions(self, now=None):
        """A list of next actions currently visible in the given contexts."""
        if not now:
            now = datetime.datetime.now()
        next_actions = []
        matcher = lambda x: \
            self._VisibleNextAction(x, now) and self._OkContexts(x)
        for file in self._files.values():
            next_actions.extend(self.Collect(node=file, matcher=matcher))
        for project in self.ProjectsWithoutNextActions():
            vis = project.DateState(now) != libvtd.node.DateStates.invisible
            if vis and self._OkContexts(project):
                next_actions.append(libvtd.node.NeedsNextActionStub(project))
        return next_actions

    def RecurringActions(self, now=None):
        """A list of recurring actions visible given the current contexts."""
        if not now:
            now = datetime.datetime.now()
        recurs = []
        matcher = lambda x: (self._VisibleRecurringAction(x, now)
                             and self._OkContexts(x))
        for file in self._files.values():
            recurs.extend(self.Collect(node=file, matcher=matcher))
        return recurs

    def NextActionsWithoutContexts(self):
        """A list of NextActions which don't have a context."""
        next_actions = []
        for file in self._files.values():
            next_actions.extend(self.Collect(node=file, matcher=lambda x:
                                             isinstance(x,
                                                        libvtd.node.NextAction)
                                             and not x.contexts))
        return next_actions

    def Waiting(self, now=None):
        """The GTD 'Waiting For' list."""
        if not now:
            now = datetime.datetime.now()
        waiting = []
        wait_matcher = lambda x: self._VisibleAction(x, now) and x.waiting
        for file in self._files.values():
            waiting.extend(self.Collect(node=file, matcher=wait_matcher))
        return waiting

    def _Blocked(self, node):
        """Checks whether the node is blocked.

        Note that a node is also blocked if any ancestor is.
        """
        # Base case for recursion.
        if not node:
            return False

        try:
            for b in node.blockers:
                if self._BlockerExists(id=b):
                    return True
        except AttributeError:
            # This Node does not have the concept of blockers; hence, it's not
            # blocked.
            return False

        return self._Blocked(node.parent)

    def _BlockerExists(self, id):
        """Checks whether a Node with the given id exists."""

        def Matcher(node):
            try:
                return id in node.ids and not node.done
            except AttributeError:
                return False

        for file in self._files.values():
            if self.FindFirstNode(node=file, matcher=Matcher):
                return True

        return False

    def _OkContexts(self, node):
        """Checks whether node passes the contexts filter.

        Args:
            node: A Node object to check.

        Returns:
            True if node shows up on at least one current 'include' context,
            and none of the 'exclude' contexts; otherwise False.
        """
        node_included = False
        for node_context in node.contexts:
            if any([c == node_context for c in self._contexts_to_exclude]):
                return False
            if any([c == node_context for c in self._contexts_to_include]):
                node_included = True
        return node_included or not self._contexts_to_include

    def SetContexts(self, include=None, exclude=None):
        """Set the active contexts for this object.

        Args:
            include: A list of contexts to include: only NextActions with a
                context from this list will be included in NextActions().
            exclude: A list of contexts to exclude: no NextAction having any of
                these contexts can appear in NextActions().
        """
        self._contexts_to_include = include if include else []
        self._contexts_to_exclude = exclude if exclude else []

    def ProjectsWithoutNextActions(self):
        """The list of libvtd.node.Project items which lack Next Actions."""
        def Matcher(x):
            """Specialized matcher for projects without next actions."""
            if not isinstance(x, libvtd.node.Project) or x.done:
                return False
            for child in x.children:
                if ((isinstance(child, libvtd.node.NextAction)
                        or isinstance(child, libvtd.node.Project))
                        and not child.done):
                    return False
            return True

        projects = []
        for file in self._files.values():
            projects.extend(self.Collect(node=file, matcher=Matcher))
        return projects
