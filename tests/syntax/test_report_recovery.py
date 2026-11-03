import unittest
from todo_lib.syntax import parse, UsageError, render_help

class OverrideGrammar(unittest.TestCase):
    def test_normal_placement_and_offline_help(self):
        for args in (['report', '--final', '--override'], ['report', '--override', '--final'], ['--color=never', 'report', '--override', '--final']):
            request = parse(args)
            self.assertTrue(request.option('override'))
        text = render_help('report')
        for word in ('--override', 'cached fallback', 'not automatically retried', 'no extra prompt'):
            self.assertIn(word, text)

    def test_invalid_combinations(self):
        for args in (['report', '--override'], ['report', '--final', '--override', '--override'], ['report', '--final', '--override', '--yes'], ['report', '--final', '--override', '--since', 'today'], ['report', '--override', '--show-cursor'], ['now', '--override'], ['report', '--final', '--override=true'], ['report', '--final', '--override', '--unknown']):
            with self.subTest(args=args), self.assertRaises(UsageError):
                parse(args)
