import datetime
import re


class _Enum(tuple):
    """A simple way to make enum types."""
    __getattr__ = tuple.index


DateStates = _Enum(['invisible', 'ready', 'due', 'late'])


class Node(object):

    # The "_level" of a Node defines nesting behaviour.  No Node may nest
    # inside a Node with a smaller _level.  Only certain types of Node may nest
    # within Nodes of the *same* _level (depending on _can_nest_same_type).
    #
    # The actual value of _level doesn't matter; it's only used for relative
    # comparisons.
    _level = 0
    _can_nest_same_type = False

    # Handy patterns and regexes.
    # Tags either start at the beginning of the line, or with a space.
    _r_start = r'(^| )'
    _r_end = r'(?=[.!?)"'';:]*(\s|$))'
    _date_format = r'%Y-%m-%d'
    _datetime_format = r'%Y-%m-%d %H:%M'
    _date_pattern = (r'(?P<datetime>\d{4}-\d{2}-\d{2}'
                     r'( (?P<time>\d{2}:\d{2}))?)')
    _due_within_pattern = r'(\((?P<due_within>\d+)\))?'
    _due_date_pattern = re.compile(_r_start + r'<' + _date_pattern +
                                   _due_within_pattern + _r_end)
    _vis_date = re.compile(_r_start + r'>' + _date_pattern + _r_end)
    _context = re.compile(_r_start + r'(?P<prefix>@{1,2})(?P<cancel>!?)' +
                          r'(?P<context>\w+)' + _r_end)
    _priority_pattern = re.compile(_r_start + r'@p:(?P<priority>[01234])' +
                                   _r_end)

    def __init__(self, text, priority, *args, **kwargs):
        super(Node, self).__init__(*args, **kwargs)

        # Public properties.
        self._text = text
        self._priority = priority
        self.children = []
        self.parent = None
        self.due_date = None
        self.visible_date = None

        # Private variables
        self._contexts = []
        self._canceled_contexts = []

    def AddChild(self, other):
        """Add 'other' as a child of 'self' (and 'self' as parent of 'other').

        Args:
            other: Another Node object.

        Returns:
            A boolean indicating success.
        """
        if not self.CanContain(other):
            return False
        other.parent = self
        self.children.append(other)
        return True

    def CanContain(self, other):
        return self._level < other._level or (self._level == other._level and
                                              self._can_nest_same_type)

    def AddContext(self, context, cancel=False):
        """Add context to this Node's contexts list."""
        context_list = self._canceled_contexts if cancel else self._contexts
        if context not in context_list:
            context_list.append(context.lower())

    @property
    def contexts(self):
        context_list = list(self._contexts)
        if self.parent:
            context_list.extend(self.parent.contexts)
        return [c for c in context_list if c not in self._canceled_contexts]

    @property
    def priority(self):
        if self._priority is not None:
            return self._priority
        return self.parent.priority if self.parent else None

    @property
    def text(self):
        return self._text.strip()

    def DebugName(self):
        old_name = ('{} :: '.format(self.parent.DebugName()) if self.parent
                    else '')
        return '{}[{}] {}'.format(old_name, self.__class__.__name__, self.text)

    def ParseDueDate(self, match):
        """Parses the due date from a match object.

        Args:
            match: A match from the self._due_date_pattern regex.

        Returns:
            The text to replace match with.  If successful, this should be the
            empty string; else, the original text.
        """
        strptime_format = (self._datetime_format if match.group('time')
                           else self._date_format)
        try:
            date = datetime.datetime.strptime(match.group('datetime'),
                                              strptime_format)
            self.due_date = date

            # Date-only due dates occur at the *end* of the day.
            if not match.group('time'):
                self.due_date = (self.due_date +
                                 datetime.timedelta(days=1, seconds=-1))

            due_within = match.group('due_within')
            days_before = (int(due_within) if due_within else 1)
            self.ready_date = (self.due_date -
                               datetime.timedelta(days=days_before))
            return ''
        except ValueError:
            return match.group(0)

    def ParseVisDate(self, match):
        """Parses the visible-after date from a match object.

        Args:
            match: A match from the self._vis_date regex.

        Returns:
            The text to replace match with.  If successful, this should be the
            empty string; else, the original text.
        """
        strptime_format = (self._datetime_format if match.group('time')
                           else self._date_format)
        try:
            date = datetime.datetime.strptime(match.group('datetime'),
                                              strptime_format)
            self.visible_date = date
            return ''
        except ValueError:
            return match.group(0)

    def ParseContext(self, match):
        """Parses the context from a match object.

        Args:
            match: A match from the self._context regex.

        Returns:
            The text to replace match with.  If successful, this should be
            either the empty string, or (for @@-prefixed contexts) the bare
            context name; else, the original text.
        """
        cancel = (match.group('cancel') == '!')
        self.AddContext(match.group('context'), cancel=cancel)
        return (' ' + match.group('context') if match.group('prefix') == '@@'
                else '')

    def ParsePriority(self, match):
        """Parses the priority from a match object.

        Args:
            match: A match from the self._priority_pattern regex.

        Returns:
            The text to replace match with, i.e., the empty string.
        """
        self._priority = int(match.group('priority'))
        return ''

    def _CanAbsorbText(self, text):
        """Indicates whether this Node can absorb the given line of text.

        The default is to absorb only if there is no pre-existing text;
        subclasses may specialize this behaviour.
        """
        return not self._text

    def AbsorbText(self, text):
        """Strip out special sequences and add whatever's left to the text.

        "Special sequences" include sequences which *every* Node type is
        allowed to have: visible-dates, due-dates, contexts,
        priorities, etc.

        Args:
            text: The text to parse and add.

        Returns:
            A boolean indicating success.  Note that if it returns False, this
            Node must be in the same state as it was before the function was
            called.
        """
        if not self._CanAbsorbText(text):
            return False

        # Tokens which are common to all Node instances: due date;
        # visible-after date; contexts; priority.
        text = self._due_date_pattern.sub(self.ParseDueDate, text)
        text = self._vis_date.sub(self.ParseVisDate, text)
        text = self._context.sub(self.ParseContext, text)
        text = self._priority_pattern.sub(self.ParsePriority, text)

        # Optional extra parsing and stripping for subclasses.
        text = self._ParseSpecializedTokens(text)

        self._text = (self._text + '\n' if self._text else '') + text.strip()
        return True

    def _ParseSpecializedTokens(self, text):
        """Parse tokens which only make sense for a particular subclass.

        For example, a field for the time it takes to complete a task only
        makes sense for the NextAction subclass.
        """
        return text


class IndentedNode(Node):
    """A Node which supports multiple lines, at a given level of indentation.
    """

    def __init__(self, indent=0, *args, **kwargs):
        super(IndentedNode, self).__init__(*args, **kwargs)
        self.indent = indent
        self.text_indent = indent + 2

    def CanContain(self, other):
        return super(IndentedNode, self).CanContain(other) and (self.indent <
                                                                other.indent)

    def _CanAbsorbText(self, text):
        # If we have no text, don't worry about checking indenting.
        if not self._text:
            return True

        # For subsequent text: accept blank lines, or text which is
        # sufficiently indented.
        return (not text.strip()) or text.startswith(' ' * self.text_indent)


class DoableNode(Node):
    """A Node which can be sensibly marked as DONE."""

    _done_pattern = re.compile(Node._r_start +
                               r'\((DONE|WONTDO)( {})?\)'.format(
                                   Node._date_pattern)
                               + Node._r_end)
    _id_word = r'(?P<id>\w+)'
    _id_pattern = re.compile(Node._r_start + r'#' + _id_word + Node._r_end)
    _after_pattern = re.compile(Node._r_start + r'@after:' + _id_word +
                                Node._r_end)

    def __init__(self, *args, **kwargs):
        super(DoableNode, self).__init__(*args, **kwargs)
        self.done = False

        # A list of ids for DoableNode objects which must be marked DONE before
        # *this* DoableNode will be visible.
        self.blockers = []

        # A list of ids for this DoableNode.  The initial id is for internal
        # usage only; note that it can never match the _id_pattern regex.
        # Other IDs may be added using the _id_pattern regex.
        self.ids = ['*{}'.format(id(self))]

    def DateState(self, now):
        """The state of this node relative to now: late; ready; due; invisible.

        Args:
            now: datetime.datetime object giving the current time.

        Returns:
            An element of the DateStates enum.
        """
        if self.visible_date and now < self.visible_date:
            return DateStates.invisible
        if self.due_date is None:
            return DateStates.ready
        if self.due_date < now:
            return DateStates.late
        if self.ready_date < now:
            return DateStates.due
        return DateStates.ready

    def ParseAfter(self, match):
        self.blockers.extend([match.group('id')])
        return ''

    def ParseDone(self, match):
        self.done = True
        return ''

    def ParseId(self, match):
        self.ids.extend([match.group('id')])
        return ''

    def _ParseSpecializedTokens(self, text):
        """Parse tokens specific to indented blocks.
        """
        text = super(DoableNode, self)._ParseSpecializedTokens(text)
        text = self._done_pattern.sub(self.ParseDone, text)
        text = self._id_pattern.sub(self.ParseId, text)
        text = self._after_pattern.sub(self.ParseAfter, text)
        return text


class File(Node):

    _level = Node._level + 1
    _can_nest_same_type = False

    # These compiled regexes inidicate line patterns which correspond to the
    # various Node subclasses.  Each should have a named matchgroup named
    # 'text', to indicate the "core" text, i.e., everything *except* the
    # pattern.  e.g.,
    # Section:
    #   = <Core text> =
    # NextAction:
    #     @ <Core text>
    # etc.
    _indent = r'(?P<indent>^\s*)'
    _text_pattern = r' (?P<text>.*)'
    _section_pattern = re.compile(r'^(?P<level>=+)' + _text_pattern +
                                  r' (?P=level)$')
    _next_action_pattern = re.compile(_indent + r'@' + _text_pattern)
    _comment_pattern = re.compile(_indent + r'\*' + _text_pattern)
    _project_pattern = re.compile(_indent + r'(?P<type>[#-])' + _text_pattern)

    def __init__(self, file_name=None, *args, **kwargs):
        super(File, self).__init__(text='', priority=None, *args, **kwargs)
        self.bad_lines = []

        try:
            # Read file contents and create a tree of Nodes from them.
            with open(file_name) as vtd_file:
                # Parse the file, one line at a time, as follows.
                # Try creating a Node from the line.
                # - If successful, make the node a child of the previous node
                #   -- or at least, the first *ancestor* of the previous node
                #   which can contain the new one.
                # - If unsuccessful, try absorbing the text into the previous
                #   node.
                previous_node = self
                for (line_num, line) in enumerate(vtd_file):
                    new_node = self.CreateNodeFromLine(line)
                    if new_node:
                        while (previous_node and not
                               previous_node.AddChild(new_node)):
                            previous_node = previous_node.parent
                        previous_node = new_node
                    else:
                        if not previous_node.AbsorbText(line):
                            self.bad_lines.append((line_num, line))
        except IOError:
            print 'Warning: file ''{}'' does not exist.'.format(file_name)
        except TypeError:
            print 'Dummy file (no file name supplied).'

    @staticmethod
    def _CreateCorrectNodeType(text):
        """Creates the Node object and returns the raw text.

        Args:
            text: The line of text to parse.

        Returns:
            A tuple (new_node, raw_text):
                new_node: An instance of the appropriate Node subclass.
                raw_text: Whatever text is leftover after the ID pattern has
                    been stripped out, but *before* other information (e.g.,
                    due dates, priority, etc.) has been stripped out.
        """
        section_match = File._section_pattern.match(text)
        if section_match:
            section = Section(level=len(section_match.group('level')))
            return (section, section_match.group('text'))

        project_match = File._project_pattern.match(text)
        if project_match:
            is_ordered = (project_match.group('type') == '#')
            indent = len(project_match.group('indent'))
            project = Project(is_ordered=is_ordered, indent=indent)
            return (project, project_match.group('text'))

        next_action_match = File._next_action_pattern.match(text)
        if next_action_match:
            indent = len(next_action_match.group('indent'))
            action = NextAction(indent=indent)
            return (action, next_action_match.group('text'))

        comment_match = File._comment_pattern.match(text)
        if comment_match:
            indent = len(comment_match.group('indent'))
            comment = Comment(indent=indent)
            return (comment, comment_match.group('text'))

        return (None, '')

    def _CanAbsorbText(self, unused_text):
        return False

    @staticmethod
    def CreateNodeFromLine(line):
        """Create the specific type of Node which this line represents.

        Args:
            line: A line of text.

        Returns:
            An instance of a Node subclass, or None if this line doesn't
            represent a valid Node.
        """
        (new_node, raw_text) = File._CreateCorrectNodeType(line)
        if new_node:
            new_node.AbsorbText(raw_text)
        return new_node


class Section(Node):

    _level = File._level + 1
    _can_nest_same_type = True

    def __init__(self, level=1, text=None, priority=None, *args, **kwargs):
        super(Section, self).__init__(text=text, priority=priority, *args,
                                      **kwargs)
        self.level = level

    def CanContain(self, other):
        if issubclass(other.__class__, Section):
            return self.level < other.level
        return super(Section, self).CanContain(other)


class Project(DoableNode, IndentedNode):

    _level = Section._level + 1
    _can_nest_same_type = True

    def __init__(self, is_ordered=False, text=None, priority=None, *args,
                 **kwargs):
        super(Project, self).__init__(text=text, priority=priority, *args,
                                      **kwargs)
        self.ordered = is_ordered

    def AddChild(self, other):
        if super(Project, self).AddChild(other):
            if self.ordered and isinstance(other, DoableNode):
                # If this Project is ordered, the new DoableNode will be
                # blocked by the most recent not-done DoableNode child.
                last_doable_node = None
                for child in self.children:
                    if (isinstance(child, DoableNode) and not child.done and
                            child != other):
                        last_doable_node = child
                if last_doable_node and last_doable_node != other:
                    temp_id = last_doable_node.ids[0]
                    other.blockers.extend([temp_id])
            return True
        return False


class NextAction(DoableNode, IndentedNode):

    _level = Project._level + 1
    _time = re.compile(Node._r_start + r'@t:(?P<time>\d+)' + Node._r_end)

    def __init__(self, text=None, priority=None, *args, **kwargs):
        super(NextAction, self).__init__(text=text, priority=priority, *args,
                                         **kwargs)

    def ParseTime(self, match):
        """Parses the time from a match object.

        Args:
            match: A match from the self._time regex.

        Returns:
            The text to replace match with, i.e., the empty string.
        """
        self.minutes = int(match.group('time'))
        return ''

    def _ParseSpecializedTokens(self, text):
        """Parse NextAction-specific tokens.
        """
        text = super(NextAction, self)._ParseSpecializedTokens(text)
        text = self._time.sub(self.ParseTime, text)
        return text


class Comment(IndentedNode):

    _level = NextAction._level + 1
    _can_nest_same_type = True

    def __init__(self, text=None, priority=None, *args, **kwargs):
        super(Comment, self).__init__(text=text, priority=priority, *args,
                                      **kwargs)
