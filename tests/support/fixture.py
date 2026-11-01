"""Standalone fixture ownership, separate from unittest's executable cases."""
from contextlib import ExitStack


class Fixture:
    """Run reusable setup with assertions supplied by the owning test case."""

    def __init__(self, case):
        self.case = case
        self._cleanups = ExitStack()
        case.addCleanup(self.close)
        try:
            self.setUp()
        except BaseException:
            self.close()
            raise

    def addCleanup(self, function, *args, **kwargs):
        self._cleanups.callback(function, *args, **kwargs)

    def close(self):
        self._cleanups.close()

    def __getattr__(self, name):
        if name.startswith('assert'):
            return getattr(self.case, name)
        raise AttributeError(name)
