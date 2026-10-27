"""Blank inbound identity across the real comment workflow and request boundary.

Raw fixtures cite pinned api-v1.openapi.json NoteSyncView.content/default and Sync
Task comments/note_update. These are synthetic responses, not live traffic.
"""
import unittest
from todo_lib import domain as d
from todo_lib import presentation as p
from todo_lib.syntax import InputError
from todo_lib.workflows.comments import encode_buffer, decode_buffer
from tests.workflows.comments import test_workflow as base
from tests.adapter.current.test_current import note


class ToleranceTests(unittest.TestCase):
    setUp = base.WorkflowTests.setUp
    refresh = base.WorkflowTests.refresh
    owner_comments = base.WorkflowTests.owner_comments
    editor = base.WorkflowTests.editor
    save = base.WorkflowTests.save
    edit = base.WorkflowTests.edit
    operation = base.WorkflowTests.operation

    def test_blank_unchanged_crlf_then_fill_same_id_omits_attachment(self):
        self.notes = [note('blank', 'C', content=' \t\r\n', posted_at=base.OLD,
                           file_attachment={'file_name': 'synthetic'})]
        self.refresh()
        self.editor('assert "[no text]" not in text\npath.write_bytes(text.replace("\\n", "\\r\\n").encode())')
        result = self.edit()
        self.assertEqual(result.status, 0)
        self.assertFalse(self.wire.commands)
        original = self.owner_comments()[0]
        self.assertEqual((original.id, original.item_id), ('blank', 'C'))
        self.assertEqual(original.body, ' \t\n')
        self.refresh()
        self.save(encode_buffer((original,)).replace('\n\n\n[new]', '\nfilled\n\n[new]'))
        filled = [note('blank', 'C', content='filled', posted_at=base.OLD)]
        self.refresh()  # Refresh again after the editor before applying changes.
        self.operation('note_update', {'id': 'blank', 'content': 'filled'}, filled)
        result = self.edit()
        self.assertEqual(result.status, 0)
        self.assertEqual(self.owner_comments()[0].id, 'blank')
        self.assertEqual(self.owner_comments()[0].body, 'filled')

    def test_empty_new_explicit_and_nonblank_edits_remain_invalid(self):
        crlf = d.Comment('crlf', 'C', 'first\r\nsecond', None)
        self.assertEqual(decode_buffer(encode_buffer((crlf,)).replace('\n', '\r\n'), (crlf,)).changes, ())
        c = d.Comment('blank', 'C', '', None)
        self.assertEqual(decode_buffer(encode_buffer((c,)), (c,)).changes, ())
        self.assertTrue(decode_buffer('[new]\n', (c,)).delete_all)
        with self.assertRaises(d.DomainError):
            decode_buffer('[id: nonblank posted: none]\n\n[new]\n',
                          (d.Comment('nonblank', 'C', 'body'),))
        with self.assertRaises(d.DomainError): decode_buffer('[new]\n\n[new]\nbody', ())
        from todo_lib.syntax import parse
        for args in (['comment', 'Leaf', '--', ''], ['done', 'Leaf', '--comment', '']):
            with self.subTest(args=args), self.assertRaises((d.DomainError, ValueError)):
                parse(args)

    def test_removing_blank_block_keeps_delete_all_confirmation(self):
        self.notes = [note('blank', 'C', content='', posted_at=base.OLD)]
        self.refresh()
        self.save('[new]\n')
        self.workflow.streams = p.OriginalStreams(base.Terminal('n\n'), base.Terminal(), base.StringIO())
        with self.assertRaises(InputError): self.edit()
        self.assertFalse(self.wire.commands)
        self.assertEqual(self.owner_comments()[0].id, 'blank')
        self.refresh()
        self.workflow.streams = p.OriginalStreams(base.Terminal('yes\n'), base.Terminal(), base.StringIO())
        self.refresh()
        self.operation('note_delete', {'id': 'blank'}, [])
        result = self.edit()
        self.assertEqual(result.status, 0)
        self.assertIn('1 deleted', result.document.stdout)
        self.assertFalse(self.owner_comments())
