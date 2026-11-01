"""In-memory terminal streams for interactive workflow probes."""
from io import StringIO


class Terminal(StringIO):
    def isatty(self):
        return True
