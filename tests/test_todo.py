import datetime as dt
import importlib.util
import importlib.machinery
import io
import pathlib
import contextlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("todo_module", str(ROOT / "todo"))
SPEC = importlib.util.spec_from_loader("todo_module", LOADER)
todo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(todo)


class TodoPureTests(unittest.TestCase):
    def test_priority_mapping(self):
        self.assertEqual(todo.cli_priority_to_api(1), 4)
        self.assertEqual(todo.cli_priority_to_api(4), 1)
        self.assertEqual(todo.api_priority_to_cli(4), 1)
        self.assertEqual(todo.api_priority_to_cli(1), 4)

    def test_business_days_skip_weekend(self):
        friday = dt.date(2026, 6, 5)
        self.assertEqual(todo.add_business_days(friday, 2), dt.date(2026, 6, 9))

    def test_hidden_category_normalization(self):
        parser = todo.configparser.ConfigParser()
        parser.add_section("main")
        parser.set("main", "hidden_from_now", "Someday, Ideas")
        cfg = todo.Config(parser)
        self.assertEqual(cfg.hidden_from_now, ["someday", "ideas"])

    def test_category_projects_are_child_projects(self):
        cache = todo.Cache({
            "projects": [
                {"id": "root", "name": "Work"},
                {"id": "eng", "name": "Engineering", "parent_id": "root"},
                {"id": "other", "name": "Other", "parent_id": None},
            ],
            "sections": [],
            "labels": [],
            "items": [],
            "notes": [],
        })
        cats = todo.category_projects(cache, "root")
        self.assertEqual([c["name"] for c in cats], ["Engineering"])
        self.assertEqual(todo.category_project_by_name(cache, "root", "engineering")["id"], "eng")

    def test_merge_deletes_objects(self):
        existing = [{"id": "1", "name": "old"}, {"id": "2", "name": "keep"}]
        incoming = [{"id": "1", "is_deleted": True}, {"id": "3", "name": "new"}]
        merged = todo.merge_resource(existing, incoming)
        ids = sorted(obj["id"] for obj in merged)
        self.assertEqual(ids, ["2", "3"])

    def test_format_duration(self):
        delta = dt.timedelta(days=2, hours=3, minutes=4)
        self.assertEqual(todo.format_duration(delta), "2d 3h")
        self.assertEqual(todo.format_duration(dt.timedelta(hours=1, minutes=20)), "1h 20m")

    def test_format_due_date_only(self):
        today = todo.today_local()
        item = {"due": {"date": today.isoformat()}}
        self.assertEqual(todo.format_due(item), "due:today")

    def test_due_when_accepts_local_datetime_in_date_field(self):
        item = {"due": {"date": "2026-06-11T16:00:00", "timezone": None}}
        self.assertIsInstance(todo.due_when(item), dt.datetime)

    def test_report_skips_old_recurring_completion(self):
        since = dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc)
        until = dt.datetime(2026, 6, 10, tzinfo=dt.timezone.utc)
        event = {
            "event_date": "2026-06-04T15:32:51Z",
            "event_type": "completed",
            "extra_data": {
                "content": "GK call",
                "is_recurring": True,
                "completed_due_date": "2026-04-09T14:00:00Z",
            },
            "object_id": "task1",
            "object_type": "item",
        }
        report = todo.build_report(todo.Cache(todo.Cache.empty()), {"project"}, since, until, [event])
        self.assertNotIn("GK call", report)

    def test_report_omits_duplicate_completion_detail(self):
        since = dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc)
        until = dt.datetime(2026, 6, 10, tzinfo=dt.timezone.utc)
        event = {
            "event_date": "2026-06-04T15:32:51Z",
            "event_type": "completed",
            "extra_data": {"content": "deliver release"},
            "object_id": "task1",
            "object_type": "item",
        }
        report = todo.build_report(todo.Cache(todo.Cache.empty()), {"project"}, since, until, [event])
        self.assertIn("- deliver release", report)
        self.assertNotIn("  - deliver release", report)

    def test_note_event_uses_parent_task_id(self):
        self.assertEqual(
            todo.event_task_id({
                "object_type": "note",
                "object_id": "note1",
                "parent_item_id": "task1",
            }),
            "task1",
        )

    def test_report_groups_by_category(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        since = dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc)
        until = dt.datetime(2026, 6, 10, tzinfo=dt.timezone.utc)
        event = {
            "event_date": "2026-06-04T15:32:51Z",
            "event_type": "completed",
            "extra_data": {"content": "deliver release"},
            "object_id": "task1",
            "object_type": "item",
            "parent_project_id": "gate",
        }
        report = todo.build_report(cache, {"gate"}, since, until, [event])
        self.assertIn("Finished\nOperations\n- deliver release", report)

    def test_report_note_uses_completed_item_context(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        since = dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc)
        until = dt.datetime(2026, 6, 10, tzinfo=dt.timezone.utc)
        events = [
            {
                "event_date": "2026-06-04T15:32:51Z",
                "event_type": "completed",
                "extra_data": {"content": "deliver release"},
                "object_id": "task1",
                "object_type": "item",
                "parent_project_id": "gate",
            },
            {
                "event_date": "2026-06-04T15:32:50Z",
                "event_type": "added",
                "extra_data": {"content": "Done: delivered release"},
                "object_id": "note1",
                "object_type": "note",
                "parent_item_id": "task1",
                "parent_project_id": "gate",
            },
        ]
        report = todo.build_report(cache, {"gate"}, since, until, events)
        self.assertIn("- deliver release\n  - Done: delivered release", report)
        self.assertNotIn("\n- Done: delivered release\n", report)

    def test_task_list_prints_all_open_steps(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        cache.data["items"] = [
            {"id": "task1", "project_id": "gate", "content": "Deliver release", "priority": 1},
            {"id": "s1", "project_id": "gate", "parent_id": "task1", "content": "check dashboard"},
            {"id": "s2", "project_id": "gate", "parent_id": "task1", "content": "close build"},
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            todo.print_task_list(cache, [cache.data["items"][0]], show_steps=True)
        self.assertIn("    - check dashboard", out.getvalue())
        self.assertIn("    - close build", out.getvalue())

    def test_show_prints_steps_and_comments(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        cache.data["items"] = [
            {"id": "task1", "project_id": "gate", "content": "Deliver release", "priority": 3},
            {"id": "s1", "project_id": "gate", "parent_id": "task1", "content": "check dashboard"},
            {"id": "s2", "project_id": "gate", "parent_id": "task1", "content": "close build", "checked": True},
        ]
        cache.data["notes"] = [{
            "id": "n1",
            "item_id": "task1",
            "content": "Progress: checked table",
            "posted_at": "2026-06-07T14:00:00Z",
        }]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            todo.print_task_detail(cache, cache.data["items"][0])
        text = out.getvalue()
        self.assertIn("P2  Operations  Deliver release", text)
        self.assertIn("- [ ] check dashboard", text)
        self.assertIn("- [x] close build", text)
        self.assertIn("Progress: checked table", text)

    def test_show_accepts_direct_comments(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        task = {"id": "task1", "project_id": "gate", "content": "Deliver release", "priority": 3}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            todo.print_task_detail(cache, task, comments=[{
                "content": "Web comment",
                "posted_at": "2026-06-07T14:00:00Z",
            }])
        self.assertIn("Web comment", out.getvalue())

    def test_bare_todo_prints_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = todo.main([])
        self.assertEqual(rc, 0)
        self.assertIn("commands:", out.getvalue())

    def test_help_lists_command_descriptions(self):
        parser = todo.build_parser()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            parser.print_help()
        text = out.getvalue()
        self.assertIn("now", text)
        self.assertIn("show actionable tasks", text)
        self.assertIn("report", text)
        self.assertIn("generate weekly report draft", text)


if __name__ == "__main__":
    unittest.main()
