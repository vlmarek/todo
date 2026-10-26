"""Pure buffer structure and lossless body normalization evidence."""
import unittest

from todo_lib import domain as d
from todo_lib.workflows.comments import (CommentError, encode_buffer, decode_buffer,
                                         ordered_comments)

OLD = '2026-10-21T12:00:00.123456789012348Z'
NEW = '2026-10-21T12:00:00.123456789012349Z'


def comment(identity, body='body', timestamp=OLD):
    return d.Comment(identity, 'leaf', body, d.instant_from_wire(timestamp) if timestamp else None)


class CodecTests(unittest.TestCase):
    def setUp(self):
        # Reverse IDs defeat a microsecond-truncated ordering implementation.
        self.originals = (comment('a-newer', 'newer', NEW), comment('z-older', 'older'),
                          comment('unknown', 'unknown', None))

    def test_exact_oldest_first_and_starter_roundtrip(self):
        text = encode_buffer(self.originals)
        self.assertLess(text.index('z-older'), text.index('a-newer'))
        self.assertLess(text.index('a-newer'), text.index('unknown'))
        self.assertIn('posted: none', text)
        self.assertTrue(text.endswith('[new]\n'))
        self.assertEqual(decode_buffer(text, self.originals).changes, ())
        self.assertEqual(decode_buffer(text.removesuffix('[new]\n'), self.originals).changes, ())
        self.assertEqual([c.id for c in ordered_comments(self.originals)], ['z-older', 'a-newer', 'unknown'])

    def test_selective_escape_and_whitespace_roundtrip(self):
        body = '  indented  \n\n \t\n[new]\n[id: other posted: whatever]\n\\path\n\\\\two\nend\\slash  '
        originals = (comment('c', '\n\t\n' + body + '\n \n'),)
        text = encode_buffer(originals)
        self.assertIn('  indented  \n\n \t\n\\[new]', text)
        self.assertIn('\\\\path', text)
        self.assertIn('end\\slash  ', text)
        self.assertEqual(decode_buffer(text, originals).changes, ())
        plan = decode_buffer('[new]\n\n' + text.split('\n', 1)[1].split('\n\n[new]')[0] + '\n\n', ())
        self.assertEqual(plan.changes[0].body, body)
        self.assertEqual(decode_buffer('[new]\n\\ordinary\na\\b', ()).changes[0].body,
                         '\\ordinary\na\\b')

    def test_fill_starter_and_saved_order_with_edits_first(self):
        originals = (comment('b', 'B'), comment('a', 'A'))
        saved = '[new]\nfirst\n[new]\nsecond\n[id: b posted: informational edit]\n  changed  \n\n[new]\n\t\n'
        changes = decode_buffer(saved, originals).changes
        self.assertEqual([(c.kind, c.comment_id, c.body) for c in changes],
                         [('edit', 'b', '  changed  '), ('add', None, 'first'),
                          ('add', None, 'second'), ('delete', 'a', None)])
        filled = decode_buffer(encode_buffer(originals) + 'fresh\n', originals)
        self.assertEqual([(c.kind, c.body) for c in filled.changes], [('add', 'fresh')])

    def test_timestamp_edits_are_informational(self):
        self.assertEqual(decode_buffer('[id: x posted: any display text]\nbody\n[new]\n',
                                      (comment('x'),)).changes, ())

    def test_removed_interior_header_joins_body_and_deletes_missing_id(self):
        originals = (comment('a', 'A'), comment('b', 'B'))
        saved = encode_buffer(originals).replace('[id: b posted: 2026-10-21 12:00]\n', '')
        plan = decode_buffer(saved, originals)
        self.assertEqual([(c.kind, c.comment_id, c.body) for c in plan.changes],
                         [('edit', 'a', 'A\n\nB'), ('delete', 'b', None)])
        self.assertFalse(plan.delete_all)

    def test_delete_all_and_empty_originals(self):
        for text in ('', ' \n\t\n', '[new]\n \n\t'):
            with self.subTest(text=text):
                self.assertTrue(decode_buffer(text, self.originals).delete_all)
                self.assertEqual(len(decode_buffer(text, self.originals).changes), 3)
                self.assertEqual(decode_buffer(text, ()).changes, ())
                self.assertFalse(decode_buffer(text, ()).delete_all)

    def test_entire_structure_rejects_invalid_blocks(self):
        for text in ('orphan\n[new]\nvalid', '[other]\ntext', '[id: x]\nbody',
                     '[id: alien posted: now]\nbody',
                     '[id: x posted: now]\nbody\n[id: x posted: now]\nbody',
                     '[new]\n\n[new]\nvalid', '[id: x posted: now]\n \t\n[new]\n',
                     '[new]\nvalid\n[new]\n\n[new]\n', '[new]\nvalid\x00'):
            with self.subTest(text=text), self.assertRaises((CommentError, d.DomainError)):
                decode_buffer(text, (comment('x'),))


if __name__ == '__main__':
    unittest.main()
