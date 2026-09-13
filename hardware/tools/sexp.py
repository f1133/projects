"""A small S-expression reader/writer for KiCad files.

The generator writes KiCad files by string formatting, which is fine for
emitting. Reading one back to route it needs real parsing, so this is that.
"""


def parse(text):
    """Return the nested list form of the first s-expression in `text`."""
    i, n = 0, len(text)

    def node(i):
        while i < n and text[i] in " \t\r\n":
            i += 1
        if text[i] == "(":
            i += 1
            out = []
            while True:
                while i < n and text[i] in " \t\r\n":
                    i += 1
                if text[i] == ")":
                    return out, i + 1
                v, i = node(i)
                out.append(v)
        if text[i] == '"':
            i += 1
            buf = []
            while text[i] != '"':
                if text[i] == "\\":
                    buf.append(text[i + 1])
                    i += 2
                else:
                    buf.append(text[i])
                    i += 1
            return Str("".join(buf)), i + 1
        j = i
        while i < n and text[i] not in " \t\r\n()":
            i += 1
        return text[j:i], i

    v, _ = node(0)
    return v


class Str(str):
    """A token that was quoted in the source, so it is re-quoted on output."""


def find(node, tag):
    """First direct child list whose head is `tag`."""
    for c in node:
        if isinstance(c, list) and c and c[0] == tag:
            return c
    return None


def findall(node, tag):
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def val(node, tag, idx=1, default=None):
    c = find(node, tag)
    return c[idx] if c and len(c) > idx else default


def nums(node, tag, count=2):
    c = find(node, tag)
    if not c:
        return None
    return [float(x) for x in c[1:1 + count]]
