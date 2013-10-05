import contextlib
import os
import re
import tempfile

import libvtd.node
import libvtd.trusted_system


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
