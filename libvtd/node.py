class Node(object):

    # The "_level" of a Node defines nesting behaviour.  No Node may nest
    # inside a Node with a smaller _level.  Only certain types of Node may nest
    # within Nodes of the *same* _level (depending on _can_nest).
    #
    # The actual value of _level doesn't matter; it's only used for relative
    # comparisons.
    _level = 0
    _can_nest = False

    def __init__(self, text, priority):
        super(Node, self).__init__()
        self.text = text
        self.priority = priority
        self.children = []
        self.parent = None

    def AddChild(self, other):
        if self._level > other._level or (self._level == other._level and not
                                          self._can_nest):
            return False
        other.parent = self
        self.children.append(other)
        return True


class Section(Node):

    _level = Node._level + 1
    _can_nest = True

    def __init__(self, text=None, priority=None):
        super(Section, self).__init__(text=text, priority=priority)


class Project(Node):

    _level = Section._level + 1
    _can_nest = True

    def __init__(self, text=None, priority=None):
        super(Project, self).__init__(text=text, priority=priority)


class NextAction(Node):

    _level = Project._level + 1

    def __init__(self, text=None, priority=None):
        super(NextAction, self).__init__(text=text, priority=priority)


class Comment(Node):

    _level = NextAction._level + 1
    _can_nest = True

    def __init__(self, text=None, priority=None):
        super(Comment, self).__init__(text=text, priority=priority)
