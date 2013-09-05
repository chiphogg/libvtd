import collections
import datetime
import dateutil.parser
import re


class _Enum(tuple):
    """A simple way to make enum types."""
    __getattr__ = tuple.index


# 'new' only makes sense for recurring actions.  It represents a recurring
# action which hasn't been done yet.
DateStates = _Enum(['new', 'invisible', 'ready', 'due', 'late'])
Actions = _Enum(['MarkDONE'])


def PreviousTime(date_and_time, time_string=None, due=True):
    """The last datetime before 'date_and_time' that the time was 'time'.

    Args:
        date_and_time: A datetime.datetime object.
        time_string: A string representing a time, in HH:MM format.
        due: Whether this is for a due date (as opposed to a visible date).

    Returns:
        A datetime.datetime object; the last datetime before 'date_and_time'
        whose time was 'time_string'.
    """
    try:
        time = datetime.datetime.strptime(time_string, '%H:%M').time()
    except:
        time = datetime.time()
    new_datetime = datetime.datetime.combine(date_and_time.date(), time)
    if new_datetime > date_and_time:
        new_datetime -= datetime.timedelta(days=1)
    assert new_datetime < date_and_time
    return new_datetime


def PreviousWeekday(date_and_time, weekday_string=None, due=True):
    """The last datetime before 'date_and_time' on the given day of the week.

    Args:
        date_and_time: A datetime.datetime object.
        weekday_string: A string representing a day of the week (and
            optionally, a time).
        due: Whether this is for a due date (as opposed to a visible date).

    Returns:
        A datetime.datetime object; the last datetime before 'date_and_time'
        whose time and day-of-week match 'weekday_string'.
    """
    try:
        weekday_and_time = dateutil.parser.parse(weekday_string)
        if due and not re.search('\d:\d\d', weekday_string):
            weekday_and_time = weekday_and_time.replace(hour=23, minute=59)
    except:
        weekday_and_time = dateutil.parser.parse('Sun 00:00')

    if date_and_time.weekday() == weekday_and_time.weekday():
        new_datetime = datetime.datetime.combine(date_and_time.date(),
                                                 weekday_and_time.time())
        if new_datetime > date_and_time:
            new_datetime += datetime.timedelta(days=-7)
    else:
        new_datetime = datetime.datetime.combine(
            date_and_time.date() +
            datetime.timedelta(days=-((date_and_time.weekday() -
                                       weekday_and_time.weekday()) % 7)),
            weekday_and_time.time())
    assert new_datetime < date_and_time
    return new_datetime


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
        self.children = []
        self.parent = None
        self._visible_date = None

        # Private variables
        self._contexts = []
        self._canceled_contexts = []
        self._due_date = None
        self._ready_date = None
        self._priority = priority
        self._raw_text = []
        self._text = text

        # A function which takes no arguments and returns a patch (as from
        # diff).  Default is the identity patch (i.e., the empty string).
        self._diff_functions = collections.defaultdict(lambda: lambda: '')

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
    def due_date(self):
        parent_due_date = self.parent.due_date if self.parent else None
        if not self._due_date:
            return parent_due_date
        if not parent_due_date:
            return self._due_date
        return min(self._due_date, parent_due_date)

    @property
    def ready_date(self):
        parent_ready_date = self.parent.ready_date if self.parent else None
        if not self._ready_date:
            return parent_ready_date
        if not parent_ready_date:
            return self._ready_date
        return min(self._ready_date, parent_ready_date)

    @property
    def visible_date(self):
        parent_visible_date = self.parent.visible_date if self.parent else None
        if not self._visible_date:
            return parent_visible_date
        if not parent_visible_date:
            return self._visible_date
        return max(self._visible_date, parent_visible_date)

    @property
    def file_name(self):
        return self.parent.file_name if self.parent else None

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
            self._due_date = date

            # Date-only due dates occur at the *end* of the day.
            if not match.group('time'):
                self._due_date = (self._due_date +
                                  datetime.timedelta(days=1, seconds=-1))

            due_within = match.group('due_within')
            days_before = (int(due_within) if due_within else 1)
            self._ready_date = (self._due_date -
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
            self._visible_date = date
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

    def Patch(self, action):
        """A patch to perform the requested action.

        Should be applied against this Node's file, if any.

        Args:
            action: An element of the libvtd.node.Actions enum.

        Returns:
            A string equivalent to the output of the 'diff' program; when
            applied to the file, it performs the requested action.
        """
        assert action in range(len(Actions))
        return self._diff_functions[action]()

    def _CanAbsorbText(self, text):
        """Indicates whether this Node can absorb the given line of text.

        The default is to absorb only if there is no pre-existing text;
        subclasses may specialize this behaviour.
        """
        return not self._text

    def AbsorbText(self, text, raw_text=None):
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
        self._raw_text.append(raw_text if raw_text else text)

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

    # Patterns related to recurring actions.
    _last_done_pattern = re.compile(Node._r_start +
                                    r'\(LASTDONE {}\)'.format(
                                        Node._date_pattern)
                                    + Node._r_end)
    _recur_unit_pattern = r'(?P<unit>day|week)'
    _recur_min_pattern = r'(?P<min>\d+)'
    _recur_max_pattern = r'(?P<max>\d+)'
    _recur_subunit_vis_pattern = r'(?P<vis>[^,]+)'
    _recur_unit_boundary_pattern = r'(?P<due>[^,]+)'
    _recur_pattern = re.compile(Node._r_start +
                                r'\s*'.join([
                                    r'EVERY',
                                    # How many:
                                    r'( ({}-)?{})?'.format(_recur_min_pattern,
                                                           _recur_max_pattern),
                                    # Which units:
                                    r' {}s?'.format(_recur_unit_pattern),
                                    # Which part of the unit:
                                    r'(\[({}-)?{}\])?'.format(
                                        _recur_subunit_vis_pattern,
                                        _recur_unit_boundary_pattern),
                                ]) +
                                Node._r_end)

    # Functions which reset a datetime to the beginning of an interval
    # boundary: a day, a week, a month, etc.  This boundary can be arbitrary
    # (e.g., reset to "the previous 14th of a month" or "the previous Tuesday
    # at 17:00".)  One function for each type of interval.
    #
    # Related to recurring actions.
    #
    # Args:
    #   d: A datetime to reset.
    #   b: The boundary of the interval: a string to be parsed.
    _interval_boundary_function = {
        'day': PreviousTime,
        'week': PreviousWeekday,
    }

    # Functions which advance a datetime by some number of units.
    #
    # Related to recurring actions.
    #
    # Args:
    #   d: A datetime to advance.
    #   n: Number of units to advance.
    _date_advancing_function = {
        'day': lambda d, n: d + datetime.timedelta(days=n),
        'week': lambda d, n: d + datetime.timedelta(days=7 * n),
    }

    def __init__(self, *args, **kwargs):
        super(DoableNode, self).__init__(*args, **kwargs)
        self.done = False
        self.recurring = False
        self.last_done = None
        self._diff_functions[Actions.MarkDONE] = self._PatchMarkDone

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
        if self.recurring:
            if not self.last_done:
                return DateStates.new
            self._SetRecurringDates()
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

    def ParseLastDone(self, match):
        try:
            last_done = datetime.datetime.strptime(match.group('datetime'),
                                                   self._datetime_format)
            self.last_done = last_done
            return ''
        except ValueError:
            return match.group(0)

    def ParseRecur(self, match):
        self.recurring = True
        self._recur_max = int(match.group('max')) if match.group('max') else 1
        self._recur_min = int(match.group('min')) if match.group('min') else \
            self._recur_max
        self._recur_unit = match.group('unit')
        self._recur_unit_boundary = match.group('due')
        self._recur_subunit_visible = match.group('vis')
        return ''

    def _ParseSpecializedTokens(self, text):
        """Parse tokens specific to indented blocks.
        """
        text = super(DoableNode, self)._ParseSpecializedTokens(text)
        text = self._done_pattern.sub(self.ParseDone, text)
        text = self._id_pattern.sub(self.ParseId, text)
        text = self._after_pattern.sub(self.ParseAfter, text)
        text = self._recur_pattern.sub(self.ParseRecur, text)
        text = self._last_done_pattern.sub(self.ParseLastDone, text)
        return text

    def _PatchMarkDone(self):
        """A patch which toggles this DoableNode's 'DONE' status."""
        if not self.done:
            return '\n'.join([
                '@@ -{0} +{0} @@',
                '-{1}',
                '+{1} (DONE {2})',
                ''
            ]).format(self._line_in_file, self._raw_text[0],
                      datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
        return ''

    def _SetRecurringDates(self):
        """Set dates (visible, due, etc.) based on last-done date."""
        unit = self._recur_unit

        # Find the previous datetime (before the last-done time) which bounds
        # the time interval (day, week, month, ...).
        base_datetime = self._interval_boundary_function[unit](
            self.last_done, self._recur_unit_boundary)

        # If an action was completed after the due date, but before the next
        # visible date, associate it with the previous interval.  (An example
        # of the kind of disaster this prevents: suppose the rent is due on the
        # 1st, and we pay it on the 2nd.  Then we risk the system thinking the
        # rent is paid for the *new* month.
        if self._recur_subunit_visible:
            # This kind of operation doesn't really make sense if the task is
            # visible for the entire interval.
            previous_vis_date = self._interval_boundary_function[unit](
                self.last_done, self._recur_subunit_visible, due=False)
            # If we did the task after the due time, but before it was visible,
            # then the previous due date comes *after* the previous visible
            # date.  So, put the base datetime back in the *previous* unit.
            if base_datetime > previous_vis_date:
                base_datetime = self._date_advancing_function[unit](
                    base_datetime, -1)

        # Set visible, ready, and due dates relative to base_datetime.
        self._visible_date = self._date_advancing_function[unit](
            base_datetime, self._recur_min)
        if self._recur_subunit_visible:
            # Move the visible date forward to the subunit boundary (if any).
            # To do this, move it forward one full unit, then move it back
            # until it matches the visible subunit boundary.
            self._visible_date = self._date_advancing_function[unit](
                self._visible_date, 1)
            self._visible_date = self._interval_boundary_function[unit](
                self._visible_date, self._recur_subunit_visible, due=False)
        self._ready_date = self._date_advancing_function[unit](
            base_datetime, self._recur_max)
        self._due_date = self._date_advancing_function[unit](
            base_datetime, self._recur_max + 1)


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
        self._file_name = file_name

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
                for (line_num, line) in enumerate(vtd_file, 1):
                    raw_text = line.rstrip('\n')
                    new_node = self.CreateNodeFromLine(raw_text, line_num)
                    if new_node:
                        while (previous_node and not
                               previous_node.AddChild(new_node)):
                            previous_node = previous_node.parent
                        previous_node = new_node
                    else:
                        if not previous_node.AbsorbText(raw_text):
                            self.bad_lines.append((line_num, raw_text))
        except IOError:
            print 'Warning: file ''{}'' does not exist.'.format(file_name)
        except TypeError:
            print 'Dummy file (no file name supplied).'

    @property
    def file_name(self):
        return self._file_name

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
    def CreateNodeFromLine(line, line_num=1):
        """Create the specific type of Node which this line represents.

        Args:
            line: A line of text.

        Returns:
            An instance of a Node subclass, or None if this line doesn't
            represent a valid Node.
        """
        (new_node, text) = File._CreateCorrectNodeType(line)
        if new_node:
            new_node.AbsorbText(text, line)
            new_node._line_in_file = line_num
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


class NeedsNextActionStub(NextAction):
    """A stub to remind the user that a Project needs a NextAction."""

    _stub_text = '{MISSING Next Action}'

    def __init__(self, project, *args, **kwargs):
        super(NeedsNextActionStub, self).__init__(
            text=NeedsNextActionStub._stub_text, *args, **kwargs)
        self.parent = project
        self._diff_functions[Actions.MarkDONE] = self.parent._PatchMarkDone


class Comment(IndentedNode):

    _level = NextAction._level + 1
    _can_nest_same_type = True

    def __init__(self, text=None, priority=None, *args, **kwargs):
        super(Comment, self).__init__(text=text, priority=priority, *args,
                                      **kwargs)
