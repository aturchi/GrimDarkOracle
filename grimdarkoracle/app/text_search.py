"""Find-in-lists logic behind Ctrl+F (ui.search_widget), Tk-free.

The rows of every searchable list of a window are flattened into one
sequence of (key, text); a search moves to the next row whose text holds
the query (case-insensitive), after the previous hit, wrapping around at
the end. Ported from W40kDiviner's search dialog.
"""


def next_match(rows, query: str, after=None):
    """Key of the first row after 'after' (None: from the start) whose
    text contains 'query', with wrap-around; None if no row matches or
    the query is blank."""
    q = query.strip().lower()
    if not q or not rows:
        return None
    keys = [k for k, _t in rows]
    start = keys.index(after) + 1 if after in keys else 0
    order = rows[start:] + rows[:start]
    return next((k for k, text in order if q in str(text).lower()), None)
