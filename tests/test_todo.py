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

    def test_normalize_due_value_clear(self):
        self.assertIsNone(todo.normalize_due_value("clear"))
        self.assertIsNone(todo.normalize_due_value("-"))

    def test_normalize_due_value_days_and_hours(self):
        day_value = todo.normalize_due_value("2d")
        hour_value = todo.normalize_due_value("4h")
        self.assertIsInstance(todo.parse_iso(day_value), dt.datetime)
        self.assertIsInstance(todo.parse_iso(hour_value), dt.datetime)
        self.assertIn("T", day_value)
        self.assertIn("T", hour_value)

    def test_normalize_due_value_preserves_other_expressions(self):
        self.assertEqual(todo.normalize_due_value("tomorrow"), "tomorrow")
        self.assertEqual(todo.normalize_due_value("2026-06-12"), "2026-06-12")

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

    def test_print_comments_shows_none(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            todo.print_comments([])
        self.assertEqual(out.getvalue().strip(), "- None")

    def test_latest_comment_uses_newest_posted_time(self):
        comments = [
            {"id": "old", "content": "old", "posted_at": "2026-06-07T10:00:00Z"},
            {"id": "new", "content": "new", "posted_at": "2026-06-07T11:00:00Z"},
        ]
        self.assertEqual(todo.latest_comment(comments)["id"], "new")

    def test_append_comment_text_adds_new_line(self):
        self.assertEqual(todo.append_comment_text("", "new"), "new")
        self.assertEqual(todo.append_comment_text("old", "new"), "old\nnew")

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
        self.assertIn("task", text)
        self.assertIn("show or change tasks", text)
        self.assertIn("report", text)
        self.assertIn("generate weekly report draft", text)

    def test_category_command_lists_or_adds(self):
        parser = todo.build_parser()
        list_args = parser.parse_args(["category"])
        add_args = parser.parse_args(["category", "--add", "training"])
        self.assertEqual(list_args.cmd, "category")
        self.assertIsNone(list_args.add)
        self.assertEqual(add_args.add, "training")

    def test_categories_command_removed(self):
        parser = todo.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["categories"])

    def test_category_add_subcommand_removed(self):
        parser = todo.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["category", "add", "training"])

    def test_task_add_accepts_initial_steps(self):
        parser = todo.build_parser()
        args = parser.parse_args(["task", "--add", "operations", "Deliver next release", "check dashboard", "close build"])
        self.assertTrue(args.add)
        self.assertEqual(args.values, ["operations", "Deliver next release", "check dashboard", "close build"])

    def test_task_modes_parse(self):
        parser = todo.build_parser()
        self.assertEqual(parser.parse_args(["task", "website"]).values, ["website"])
        self.assertTrue(parser.parse_args(["task", "--done", "website", "integrated"]).done)
        self.assertTrue(parser.parse_args(["task", "--wait", "website", "waiting"]).wait)
        self.assertTrue(parser.parse_args(["task", "--resume", "website", "back"]).resume)
        self.assertTrue(parser.parse_args(["task", "--due", "website", "2d"]).due)
        self.assertTrue(parser.parse_args(["task", "--priority", "website", "1"]).priority)
        self.assertTrue(parser.parse_args(["task", "--move", "website", "engineering"]).move)

    def test_step_modes_parse(self):
        parser = todo.build_parser()
        self.assertEqual(parser.parse_args(["step", "website"]).values, ["website"])
        add_args = parser.parse_args(["step", "--add", "website", "review", "publish"])
        done_args = parser.parse_args(["step", "--done", "website", "review"])
        self.assertTrue(add_args.add)
        self.assertEqual(add_args.values, ["website", "review", "publish"])
        self.assertTrue(done_args.done)
        self.assertEqual(done_args.values, ["website", "review"])

    def test_old_verb_commands_removed(self):
        parser = todo.build_parser()
        for command in ("add", "show", "check", "wait", "resume", "done", "priority", "due", "move"):
            with self.subTest(command=command):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parser.parse_args([command])

    def test_comment_display_has_no_mode(self):
        parser = todo.build_parser()
        args = parser.parse_args(["comment", "deliver release"])
        self.assertEqual(args.values, ["deliver release"])
        self.assertFalse(args.add)
        self.assertFalse(args.edit)

    def test_comment_add_flag(self):
        parser = todo.build_parser()
        args = parser.parse_args(["comment", "--add", "deliver release", "new line"])
        self.assertTrue(args.add)
        self.assertEqual(args.values, ["deliver release", "new line"])

    def test_comment_edit_flag(self):
        parser = todo.build_parser()
        args = parser.parse_args(["comment", "--edit", "deliver release"])
        self.assertEqual(args.values, ["deliver release"])
        self.assertTrue(args.edit)

    def test_mapped_id_reads_todoist_temp_mapping(self):
        response = {
            "_todo_temp_id": "tmp1",
            "temp_id_mapping": {"tmp1": "real1"},
        }
        self.assertEqual(todo.mapped_id(response), "real1")

    def test_find_added_task_id(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["items"] = [{
            "id": "task1",
            "project_id": "gate",
            "content": "Deliver next release",
        }]
        self.assertEqual(todo.find_added_task_id(cache, "gate", "Deliver next release"), "task1")


if __name__ == "__main__":
    unittest.main()
