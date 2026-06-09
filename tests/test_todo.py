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

    def test_color_parser_flag(self):
        parser = todo.build_parser()
        args = parser.parse_args(["--color", "always", "now"])
        self.assertEqual(args.color, "always")
        args = parser.parse_args(["--color=never", "task", "website"])
        self.assertEqual(args.color, "never")

    def test_color_auto_is_plain_when_redirected(self):
        old_mode = todo.COLOR_MODE
        try:
            todo.set_color_mode("auto")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                print(todo.format_priority({"priority": 4}))
            self.assertNotIn("\033[", out.getvalue())
        finally:
            todo.set_color_mode(old_mode)

    def test_color_always_colors_task_list(self):
        old_mode = todo.COLOR_MODE
        try:
            todo.set_color_mode("always")
            cache = todo.Cache(todo.Cache.empty())
            cache.data["projects"] = [{"id": "eng", "name": "Engineering"}]
            cache.data["items"] = [{
                "id": "task1",
                "project_id": "eng",
                "content": "Urgent task",
                "priority": 4,
                "due": {"date": todo.today_local().isoformat()},
            }]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                todo.print_task_list(cache, [cache.data["items"][0]])
            self.assertIn("\033[", out.getvalue())
            self.assertIn("P1", out.getvalue())
            self.assertIn("due:today", out.getvalue())
        finally:
            todo.set_color_mode(old_mode)

    def test_no_color_disables_auto(self):
        class Tty:
            def isatty(self):
                return True

        old_mode = todo.COLOR_MODE
        old_no_color = todo.os.environ.get("NO_COLOR")
        try:
            todo.set_color_mode("auto")
            todo.os.environ["NO_COLOR"] = "1"
            self.assertFalse(todo.color_enabled(Tty()))
        finally:
            todo.set_color_mode(old_mode)
            if old_no_color is None:
                todo.os.environ.pop("NO_COLOR", None)
            else:
                todo.os.environ["NO_COLOR"] = old_no_color

    def test_format_due_date_only(self):
        today = todo.today_local()
        item = {"due": {"date": today.isoformat()}}
        self.assertEqual(todo.format_due(item), "due:today")

    def test_format_due_recurring_shows_raw_string(self):
        today = todo.today_local()
        item = {"due": {"date": today.isoformat(), "is_recurring": True, "string": "every 14 days 11:00"}}
        self.assertEqual(todo.format_due(item), "due:today ↻ every 14 days 11:00")

    def test_format_due_recurring_drops_starting_suffix(self):
        today = todo.today_local()
        item = {
            "due": {
                "date": today.isoformat(),
                "is_recurring": True,
                "string": "every 14 days 11:00 starting 23 Jun 2026",
            },
        }
        self.assertEqual(todo.format_due(item), "due:today ↻ every 14 days 11:00")

    def test_due_when_accepts_local_datetime_in_date_field(self):
        item = {"due": {"date": "2026-06-11T16:00:00", "timezone": None}}
        self.assertIsInstance(todo.due_when(item), dt.datetime)

    def test_due_when_accepts_utc_datetime_in_date_field(self):
        item = {"due": {"date": "2026-06-15T11:50:51Z"}}
        self.assertIsInstance(todo.due_when(item), dt.datetime)
        self.assertNotIn("2026-06-15T11:50:51Z", todo.format_due(item))

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

    def test_parse_due_business_days(self):
        now = dt.datetime(2026, 6, 9, 14, 30, tzinfo=dt.timezone.utc)
        result = todo.parse_due_value_local("2bd", now=now)
        self.assertIsNot(result, todo.INVALID_DUE)
        self.assertTrue(result.value.startswith("2026-06-11T"))

    def test_parse_due_weekday_excludes_today(self):
        now = dt.datetime(2026, 6, 9, 14, 30, tzinfo=dt.timezone.utc)
        result = todo.parse_due_value_local("tuesday", now=now)
        self.assertIsNot(result, todo.INVALID_DUE)
        self.assertEqual(result.value, "2026-06-16")

    def test_parse_due_weekday_time(self):
        now = dt.datetime(2026, 6, 9, 14, 30, tzinfo=dt.timezone.utc)
        result = todo.parse_due_value_local("fri 15:30", now=now)
        self.assertIsNot(result, todo.INVALID_DUE)
        self.assertTrue(result.value.startswith("2026-06-12T15:30"))

    def test_parse_due_iso_datetime_hour_only(self):
        result = todo.parse_due_value_local("2026-06-16 10")
        self.assertIsNot(result, todo.INVALID_DUE)
        self.assertTrue(result.value.startswith("2026-06-16T10:00"))

    def test_resolve_due_ask_requires_tty(self):
        class NonTty:
            def isatty(self):
                return False

        old_stdin = todo.sys.stdin
        try:
            todo.sys.stdin = NonTty()
            with self.assertRaises(todo.TodoError):
                todo.resolve_due_value("ask")
        finally:
            todo.sys.stdin = old_stdin

    def test_normalize_due_value_preserves_other_expressions(self):
        self.assertEqual(todo.normalize_due_value("tomorrow"), (todo.today_local() + dt.timedelta(days=1)).isoformat())
        self.assertEqual(todo.normalize_due_value("2026-06-12"), "2026-06-12")

    def test_waiting_due_now(self):
        today = todo.today_local()
        tomorrow = today + dt.timedelta(days=1)
        self.assertTrue(todo.waiting_due_now({"labels": ["waiting"], "due": {"date": today.isoformat()}}))
        self.assertFalse(todo.waiting_due_now({"labels": ["waiting"], "due": {"date": tomorrow.isoformat()}}))
        self.assertFalse(todo.waiting_due_now({"labels": [], "due": {"date": today.isoformat()}}))

    def test_waiting_block_preserves_description(self):
        description = "review notes"
        updated = todo.set_waiting_block(description, "wait for review", since="2026-06-07")
        self.assertIn("review notes", updated)
        self.assertEqual(todo.waiting_reason({"description": updated}), "wait for review")
        self.assertEqual(todo.remove_waiting_block(updated), "review notes")

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

    def test_build_step_context_records_parent_task(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        cache.data["items"] = [
            {"id": "task1", "project_id": "gate", "content": "Prepare new cbe"},
            {"id": "step1", "project_id": "gate", "parent_id": "task1", "content": "Seed gcc16"},
        ]
        context = todo.build_step_context(cache, seen_at="2026-06-07T18:10:00Z")
        self.assertEqual(context["step1"]["parent_task_id"], "task1")
        self.assertEqual(context["step1"]["parent_title_last_seen"], "Prepare new cbe")
        self.assertEqual(context["step1"]["category_last_seen"], "Operations")

    def test_report_completed_step_uses_current_parent_from_context(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        cache.data["items"] = [
            {"id": "task1", "project_id": "gate", "content": "Prepare new cbe renamed"},
        ]
        since = dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc)
        until = dt.datetime(2026, 6, 10, tzinfo=dt.timezone.utc)
        event = {
            "event_date": "2026-06-07T18:10:05Z",
            "event_type": "completed",
            "extra_data": {"content": "Seed gcc16"},
            "object_id": "step1",
            "object_type": "item",
            "parent_project_id": "gate",
        }
        context = {
            "step1": {
                "step_title_last_seen": "Seed gcc16",
                "parent_task_id": "task1",
                "parent_title_last_seen": "Prepare new cbe",
                "category_last_seen": "Operations",
            },
        }
        report = todo.build_report(cache, {"gate"}, since, until, [event], context)
        self.assertIn("Progress\nOperations\n- Prepare new cbe renamed\n  - Step done: Seed gcc16", report)
        self.assertNotIn("\n- Seed gcc16\n", report)

    def test_report_completed_step_without_open_parent_stays_finished(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        since = dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc)
        until = dt.datetime(2026, 6, 10, tzinfo=dt.timezone.utc)
        event = {
            "event_date": "2026-06-07T18:10:05Z",
            "event_type": "completed",
            "extra_data": {"content": "Seed gcc16"},
            "object_id": "step1",
            "object_type": "item",
            "parent_project_id": "gate",
        }
        context = {
            "step1": {
                "step_title_last_seen": "Seed gcc16",
                "parent_task_id": "task1",
                "parent_title_last_seen": "Prepare new cbe",
                "category_last_seen": "Operations",
            },
        }
        report = todo.build_report(cache, {"gate"}, since, until, [event], context)
        self.assertIn("Finished\nOperations\n- Prepare new cbe\n  - Step done: Seed gcc16", report)

    def test_report_ignores_note_events(self):
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
        self.assertIn("- deliver release", report)
        self.assertNotIn("Done: delivered release", report)

    def test_report_waiting_uses_description_reason(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        cache.data["items"] = [{
            "id": "task1",
            "project_id": "gate",
            "content": "Review URL fix",
            "labels": ["waiting"],
            "due": {"date": "2026-06-04"},
            "description": todo.set_waiting_block("", "wait for review", since="2026-06-03"),
        }]
        since = dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc)
        until = dt.datetime(2026, 6, 10, tzinfo=dt.timezone.utc)
        report = todo.build_report(cache, {"gate"}, since, until, [])
        self.assertIn("- Review URL fix", report)
        self.assertIn("  - Reason: wait for review", report)

    def test_report_command_always_refreshes(self):
        calls = []
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "root", "name": "Work"}]

        class Cfg:
            project = "Work"

        class Client:
            def activities(self, since, until, project_id):
                calls.append(("activities", project_id))
                return []

        old_load_runtime = todo.load_runtime
        old_sync_readonly = todo.sync_readonly
        old_lock_state = todo.lock_state
        old_load_step_context = todo.load_step_context
        try:
            def fake_load_runtime(readonly=False):
                calls.append(("load_runtime", readonly))
                return Cfg(), Client(), cache

            todo.load_runtime = fake_load_runtime
            todo.sync_readonly = lambda client, cache_arg: calls.append(("sync", cache_arg is cache))
            todo.lock_state = contextlib.nullcontext
            todo.load_step_context = lambda: {}
            out = io.StringIO()
            args = todo.argparse.Namespace(final=False, since="2026-06-03T00:00:00Z",
                                           until="2026-06-04T00:00:00Z")
            with contextlib.redirect_stdout(out):
                self.assertEqual(todo.cmd_report(args), 0)
        finally:
            todo.load_runtime = old_load_runtime
            todo.sync_readonly = old_sync_readonly
            todo.lock_state = old_lock_state
            todo.load_step_context = old_load_step_context
        self.assertEqual(calls, [("load_runtime", True), ("sync", True), ("activities", "root")])
        self.assertIn("Report 2026-06-03T00:00:00Z -> 2026-06-04T00:00:00Z", out.getvalue())

    def test_search_finds_task_step_description_waiting_and_comment(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "eng", "name": "Engineering"}]
        cache.data["items"] = [
            {
                "id": "task1",
                "project_id": "eng",
                "content": "config cleanup cleanup",
                "description": todo.set_waiting_block("notes mention url", "wait for review", since="2026-06-08"),
                "labels": ["waiting"],
                "priority": 3,
            },
            {"id": "step1", "project_id": "eng", "parent_id": "task1", "content": "test config cleanup"},
        ]
        comments = {"task1": [{
            "content": "REVIEW-123 covers config cleanup",
            "posted_at": "2026-06-08T08:00:00Z",
        }]}
        results = todo.search_results(cache, {"eng"}, "config cleanup", comments)
        self.assertEqual(len(results), 1)
        text = "\n".join(results[0]["matches"])
        self.assertIn("task title", text)
        self.assertIn("step open: test config cleanup", text)
        self.assertIn("comment", text)
        self.assertIn("REVIEW-123 covers config cleanup", text)

    def test_search_uses_cached_notes_by_default(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "eng", "name": "Engineering"}]
        cache.data["items"] = [{
            "id": "task1",
            "project_id": "eng",
            "content": "Task title",
        }]
        cache.data["notes"] = [{
            "id": "note1",
            "item_id": "task1",
            "content": "REVIEW-123 cached note",
            "posted_at": "2026-06-08T08:00:00Z",
        }]
        results = todo.search_results(cache, {"eng"}, "REVIEW-123")
        self.assertEqual(len(results), 1)
        self.assertIn("comment", results[0]["matches"][0])
        self.assertIn("REVIEW-123 cached note", results[0]["matches"][0])

    def test_search_finds_waiting_reason(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "eng", "name": "Engineering"}]
        cache.data["items"] = [{
            "id": "task1",
            "project_id": "eng",
            "content": "URL task",
            "description": todo.set_waiting_block("", "wait for review", since="2026-06-08"),
            "labels": ["waiting"],
        }]
        results = todo.search_results(cache, {"eng"}, "review")
        self.assertEqual(results[0]["matches"], ["waiting reason: wait for review"])

    def test_search_finds_step_context(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        context = {
            "step1": {
                "step_title_last_seen": "Seed gcc16",
                "parent_task_id": "task1",
                "parent_title_last_seen": "Prepare new cbe",
                "project_id_last_seen": "gate",
                "category_last_seen": "Operations",
            },
        }
        results = todo.search_results(cache, {"gate"}, "gcc16", step_context=context)
        self.assertEqual(len(results), 1)
        self.assertIn("step done: Seed gcc16", results[0]["matches"])

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

    def test_task_list_prints_step_due_dates(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "eng", "name": "Engineering"}]
        cache.data["items"] = [
            {"id": "task1", "project_id": "eng", "content": "utf-8 tmux wide characters", "priority": 1},
            {
                "id": "s1",
                "project_id": "eng",
                "parent_id": "task1",
                "content": "publish the release notes",
                "due": {"date": "2099-06-15"},
            },
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            todo.print_task_list(cache, [cache.data["items"][0]], show_steps=True)
        self.assertIn("    - publish the release notes due:in ", out.getvalue())

    def test_now_sort_uses_open_step_due_dates(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "eng", "name": "Engineering"}]
        cache.data["items"] = [
            {"id": "late", "project_id": "eng", "content": "later task", "priority": 1, "due": {"date": "2099-06-20"}},
            {"id": "parent", "project_id": "eng", "content": "parent with due step", "priority": 1},
            {"id": "step", "project_id": "eng", "parent_id": "parent", "content": "soon step", "due": {"date": "2099-06-10"}},
        ]
        tasks = [cache.data["items"][0], cache.data["items"][1]]
        self.assertEqual([todo.content_of(t) for t in todo.sort_now(cache, tasks)],
                         ["parent with due step", "later task"])

    def test_now_sort_ignores_completed_step_due_dates(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "eng", "name": "Engineering"}]
        cache.data["items"] = [
            {"id": "late", "project_id": "eng", "content": "later task", "priority": 1, "due": {"date": "2099-06-20"}},
            {"id": "parent", "project_id": "eng", "content": "parent with done step", "priority": 1},
            {
                "id": "step",
                "project_id": "eng",
                "parent_id": "parent",
                "content": "done soon step",
                "checked": True,
                "due": {"date": "2099-06-10"},
            },
        ]
        tasks = [cache.data["items"][0], cache.data["items"][1]]
        self.assertEqual([todo.content_of(t) for t in todo.sort_now(cache, tasks)],
                         ["later task", "parent with done step"])

    def test_now_sort_ignores_nested_step_due_dates(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "eng", "name": "Engineering"}]
        cache.data["items"] = [
            {"id": "late", "project_id": "eng", "content": "later task", "priority": 1, "due": {"date": "2099-06-20"}},
            {"id": "parent", "project_id": "eng", "content": "parent with nested step", "priority": 1},
            {"id": "direct", "project_id": "eng", "parent_id": "parent", "content": "direct step"},
            {"id": "nested", "project_id": "eng", "parent_id": "direct", "content": "nested step", "due": {"date": "2099-06-10"}},
        ]
        tasks = [cache.data["items"][0], cache.data["items"][1]]
        self.assertEqual([todo.content_of(t) for t in todo.sort_now(cache, tasks)],
                         ["later task", "parent with nested step"])

    def test_task_list_prints_waiting_reason(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        task = {
            "id": "task1",
            "project_id": "gate",
            "content": "Review URL fix",
            "labels": ["waiting"],
            "description": todo.set_waiting_block("", "wait for review", since="2026-06-07"),
        }
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            todo.print_task_list(cache, [task])
        self.assertIn("Reason: wait for review", out.getvalue())

    def test_show_prints_steps_and_comments(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["projects"] = [{"id": "gate", "name": "Operations"}]
        future_due = todo.iso_utc(todo.now_utc() + dt.timedelta(days=7))
        cache.data["items"] = [
            {"id": "task1", "project_id": "gate", "content": "Deliver release", "priority": 3},
            {"id": "s1", "project_id": "gate", "parent_id": "task1", "content": "check dashboard", "due": {"date": future_due}},
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
        self.assertIn("- [ ] check dashboard due:", text)
        self.assertNotIn(future_due, text)
        self.assertIn("- [x] close build", text)
        self.assertIn("Progress: checked table", text)

    def test_print_steps_shows_due_dates(self):
        cache = todo.Cache(todo.Cache.empty())
        future_due = todo.iso_utc(todo.now_utc() + dt.timedelta(days=7))
        task = {"id": "task1", "project_id": "gate", "content": "Deliver release"}
        cache.data["items"] = [
            task,
            {"id": "s1", "project_id": "gate", "parent_id": "task1", "content": "check dashboard", "due": {"date": future_due}},
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            todo.print_steps(cache, task)
        text = out.getvalue()
        self.assertIn("[ ] check dashboard due:", text)
        self.assertNotIn(future_due, text)

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

    def test_render_comments_edit_buffer_uses_bracket_headers(self):
        text = todo.render_comments_edit_buffer("assert.h", [{
            "id": "c1",
            "content": "first\nline",
            "posted_at": "2026-06-07T16:15:00Z",
        }])
        self.assertIn("# todo comments for: assert.h", text)
        self.assertIn("[id: c1 posted:", text)
        self.assertIn("first\nline", text)
        self.assertTrue(text.rstrip().endswith("[new]"))

    def test_parse_comments_edit_buffer(self):
        text = """# ignored
[id: c1 posted: 2026-06-07 18:15]
first

[new]
new body

[id: c2 posted: later]
second
"""
        self.assertEqual(todo.parse_comments_edit_buffer(text), [
            ("existing", "c1", "first"),
            ("new", None, "new body"),
            ("existing", "c2", "second"),
        ])

    def test_parse_header_delete_merges_into_previous_comment(self):
        text = """[id: c1 posted: now]
first

second
"""
        self.assertEqual(todo.parse_comments_edit_buffer(text), [
            ("existing", "c1", "first\n\nsecond"),
        ])

    def test_apply_comments_edit_updates_deletes_and_creates(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def add_comment(self, task_id, content):
                self.calls.append(("add", task_id, content))

            def update_comment(self, comment_id, content):
                self.calls.append(("update", comment_id, content))

            def delete_comment(self, comment_id):
                self.calls.append(("delete", comment_id))

        client = FakeClient()
        old = [
            {"id": "c1", "content": "old one"},
            {"id": "c2", "content": "old two"},
            {"id": "c3", "content": "old three"},
        ]
        edited = """[id: c1 posted: now]
new one

[id: c2 posted: now]

[new]
created one

[new]
created two
"""
        counts = todo.apply_comments_edit(client, "task1", old, edited)
        self.assertEqual(counts, {"updated": 1, "deleted": 2, "created": 2})
        self.assertEqual(client.calls, [
            ("update", "c1", "new one"),
            ("delete", "c2"),
            ("add", "task1", "created one"),
            ("add", "task1", "created two"),
            ("delete", "c3"),
        ])

    def test_add_task_comments_creates_one_comment_per_text(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def add_comment(self, task_id, content):
                self.calls.append((task_id, content))

        client = FakeClient()
        todo.add_task_comments(client, "task1", ["one", "two", "three"])
        self.assertEqual(client.calls, [
            ("task1", "one"),
            ("task1", "two"),
            ("task1", "three"),
        ])

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
        refresh_args = parser.parse_args(["category", "--refresh"])
        self.assertEqual(list_args.cmd, "category")
        self.assertIsNone(list_args.add)
        self.assertFalse(list_args.refresh)
        self.assertEqual(add_args.add, "training")
        self.assertTrue(refresh_args.refresh)

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

    def test_task_add_accepts_priority_flags(self):
        parser = todo.build_parser()
        args = parser.parse_args(["task", "--add", "-p1", "operations", "Deliver next release"])
        self.assertTrue(args.add)
        self.assertEqual(args.add_priority, 1)
        self.assertEqual(args.values, ["operations", "Deliver next release"])
        args = parser.parse_args(["task", "--add", "operations", "Deliver next release", "-p4"])
        self.assertEqual(args.add_priority, 4)
        self.assertEqual(args.values, ["operations", "Deliver next release"])

    def test_task_add_accepts_due_option(self):
        parser = todo.build_parser()
        args = parser.parse_args(["task", "--add", "--due", "7d", "operations", "Deliver next release"])
        self.assertTrue(args.add)
        self.assertEqual(args.due, "7d")
        self.assertEqual(args.values, ["operations", "Deliver next release"])
        args = parser.parse_args(["task", "--add", "operations", "Deliver next release", "--due", "7d"])
        self.assertEqual(args.due, "7d")
        self.assertEqual(args.values, ["operations", "Deliver next release"])

    def test_task_add_without_args_prints_mode_help(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = todo.main(["task", "--add"])
        self.assertEqual(rc, 1)
        self.assertIn("usage: todo task --add|--new [--due DATE] [-p1|-p2|-p3|-p4] CATEGORY TASK [STEP ...]", err.getvalue())
        self.assertIn("Create a task in CATEGORY", err.getvalue())
        self.assertNotIn("expected 2-9999", err.getvalue())

    def test_task_wait_missing_reason_prints_mode_help(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = todo.main(["task", "--wait", "Eric"])
        self.assertEqual(rc, 1)
        self.assertIn("usage: todo task --wait [--due DATE] TASK REASON", err.getvalue())
        self.assertIn("Mark TASK waiting", err.getvalue())
        self.assertNotIn("expected 2 argument", err.getvalue())

    def test_empty_noun_commands_print_command_help(self):
        cases = [
            (["task"], "usage: todo task TASK"),
            (["step"], "usage: todo step TASK"),
            (["comment"], "usage: todo comment TASK"),
            (["search"], "usage: todo search TEXT"),
        ]
        for argv, usage in cases:
            with self.subTest(argv=argv):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = todo.main(argv)
                self.assertEqual(rc, 1)
                self.assertIn(usage, err.getvalue())
                self.assertNotIn("todo:", err.getvalue())

    def test_empty_mode_flags_print_mode_help(self):
        cases = [
            (["task", "--done"], "usage: todo task --done|--close TASK [TEXT]"),
            (["task", "--add", "--done"], "usage: todo task --add|--new --done|--close [--due DATE] [-p1|-p2|-p3|-p4] CATEGORY TASK [STEP ...]"),
            (["task", "--undone"], "usage: todo task --undone|--unclose TASK"),
            (["task", "--delete"], "usage: todo task --delete [--yes] TASK"),
            (["task", "--wait"], "usage: todo task --wait [--due DATE] TASK REASON"),
            (["task", "--resume"], "usage: todo task --resume TASK TEXT"),
            (["task", "--due"], "usage: todo task --due TASK DATE"),
            (["task", "--priority"], "usage: todo task --priority TASK P"),
            (["task", "--move"], "usage: todo task --move TASK CATEGORY"),
            (["step", "--add"], "usage: todo step --add|--new [--due DATE] TASK STEP [STEP ...]"),
            (["step", "--add", "--done"], "usage: todo step --add|--new --done|--close [--due DATE] TASK STEP [STEP ...]"),
            (["step", "--done"], "usage: todo step --done|--close TASK STEP"),
            (["step", "--delete"], "usage: todo step --delete [--yes] TASK STEP"),
            (["step", "--undone"], "usage: todo step --undone|--unclose TASK STEP"),
            (["comment", "--add"], "usage: todo comment --add TASK TEXT [TEXT ...]"),
            (["comment", "--edit"], "usage: todo comment --edit TASK"),
        ]
        for argv, usage in cases:
            with self.subTest(argv=argv):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = todo.main(argv)
                self.assertEqual(rc, 1)
                self.assertIn(usage, err.getvalue())
                self.assertNotIn("todo:", err.getvalue())

    def test_task_add_partial_args_prints_mode_help(self):
        parser = todo.build_parser()
        args = parser.parse_args(["task", "--add", "Engineering"])
        with self.assertRaises(todo.TodoUsage) as cm:
            todo.cmd_task(args)
        self.assertIn("usage: todo task --add|--new [--due DATE] [-p1|-p2|-p3|-p4] CATEGORY TASK [STEP ...]",
                      str(cm.exception))
        self.assertNotIn("expected 2-9999 argument", str(cm.exception))

    def test_task_modes_parse(self):
        parser = todo.build_parser()
        self.assertEqual(parser.parse_args(["task", "website"]).values, ["website"])
        self.assertTrue(parser.parse_args(["task", "--refresh", "website"]).refresh)
        add_done_args = parser.parse_args(["task", "--add", "--done", "Engineering", "fixed bug", "tested"])
        new_closed_args = parser.parse_args(["task", "--new", "--closed", "Engineering", "fixed bug", "tested"])
        self.assertTrue(add_done_args.add)
        self.assertTrue(add_done_args.done)
        self.assertEqual(add_done_args.values, ["Engineering", "fixed bug", "tested"])
        self.assertTrue(new_closed_args.add)
        self.assertTrue(new_closed_args.done)
        self.assertEqual(new_closed_args.values, ["Engineering", "fixed bug", "tested"])
        self.assertTrue(parser.parse_args(["task", "--done", "website", "integrated"]).done)
        self.assertTrue(parser.parse_args(["task", "--close", "website", "integrated"]).done)
        self.assertTrue(parser.parse_args(["task", "--closed", "website", "integrated"]).done)
        self.assertTrue(parser.parse_args(["task", "--undone", "website"]).undone)
        self.assertTrue(parser.parse_args(["task", "--unclose", "website"]).undone)
        delete_args = parser.parse_args(["task", "--delete", "--yes", "website"])
        self.assertTrue(delete_args.delete)
        self.assertTrue(delete_args.yes)
        self.assertEqual(delete_args.values, ["website"])
        self.assertTrue(parser.parse_args(["task", "--wait", "website", "waiting"]).wait)
        wait_due_args = parser.parse_args(["task", "--wait", "--due", "7d", "website", "waiting"])
        wait_due_after_args = parser.parse_args(["task", "--wait", "website", "waiting", "--due", "7d"])
        self.assertTrue(wait_due_args.wait)
        self.assertEqual(wait_due_args.due, "7d")
        self.assertEqual(wait_due_args.values, ["website", "waiting"])
        self.assertEqual(wait_due_after_args.due, "7d")
        self.assertEqual(wait_due_after_args.values, ["website", "waiting"])
        self.assertTrue(parser.parse_args(["task", "--resume", "website", "back"]).resume)
        self.assertTrue(parser.parse_args(["task", "--due", "website", "2d"]).due)
        self.assertTrue(parser.parse_args(["task", "--priority", "website", "1"]).priority)
        self.assertTrue(parser.parse_args(["task", "--move", "website", "engineering"]).move)

    def test_task_add_priority_flag_requires_add_mode(self):
        parser = todo.build_parser()
        with self.assertRaises(todo.TodoError) as cm:
            todo.cmd_task(parser.parse_args(["task", "-p2", "website"]))
        self.assertIn("only with `todo task --add`", str(cm.exception))

    def test_task_refresh_rejected_for_mutation_modes(self):
        parser = todo.build_parser()
        with self.assertRaises(todo.TodoError) as cm:
            todo.cmd_task(parser.parse_args(["task", "--refresh", "--done", "website"]))
        self.assertIn("mutation modes refresh automatically", str(cm.exception))

    def test_task_yes_rejected_for_non_delete_modes(self):
        parser = todo.build_parser()
        with self.assertRaises(todo.TodoError) as cm:
            todo.cmd_task(parser.parse_args(["task", "--yes", "--done", "website"]))
        self.assertIn("Use --yes only", str(cm.exception))

    def test_task_priority_reports_swapped_arguments(self):
        with self.assertRaises(todo.TodoError) as cm:
            todo.parse_priority_args(["2", "config cleanup"])
        self.assertIn("priority came first", str(cm.exception))
        self.assertIn("todo task --priority config cleanup 2", str(cm.exception))

    def test_task_priority_requires_numeric_priority(self):
        with self.assertRaises(todo.TodoError) as cm:
            todo.parse_priority_args(["config cleanup", "high"])
        self.assertIn("expects priority P as 1, 2, 3, or 4", str(cm.exception))

    def test_task_add_done_dispatches_to_add(self):
        calls = []
        old_cmd_add = todo.cmd_add
        try:
            def fake_cmd_add(args):
                calls.append(args)
                return 0

            todo.cmd_add = fake_cmd_add
            parser = todo.build_parser()
            rc = todo.cmd_task(parser.parse_args(["task", "--add", "--done", "-p2", "Engineering", "fixed bug", "tested"]))
        finally:
            todo.cmd_add = old_cmd_add
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].category, "Engineering")
        self.assertEqual(calls[0].task, "fixed bug")
        self.assertEqual(calls[0].steps, ["tested"])
        self.assertEqual(calls[0].priority, 2)
        self.assertTrue(calls[0].done)

    def test_task_add_priority_dispatches_to_add(self):
        calls = []
        old_cmd_add = todo.cmd_add
        try:
            def fake_cmd_add(args):
                calls.append(args)
                return 0

            todo.cmd_add = fake_cmd_add
            parser = todo.build_parser()
            rc = todo.cmd_task(parser.parse_args(["task", "--add", "-p1", "Engineering", "fixed bug"]))
        finally:
            todo.cmd_add = old_cmd_add
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].category, "Engineering")
        self.assertEqual(calls[0].task, "fixed bug")
        self.assertEqual(calls[0].steps, [])
        self.assertEqual(calls[0].priority, 1)
        self.assertFalse(calls[0].done)

    def test_task_add_due_dispatches_to_add(self):
        calls = []
        old_cmd_add = todo.cmd_add
        try:
            def fake_cmd_add(args):
                calls.append(args)
                return 0

            todo.cmd_add = fake_cmd_add
            parser = todo.build_parser()
            rc = todo.cmd_task(parser.parse_args(["task", "--add", "--due", "7d", "Engineering", "fixed bug"]))
        finally:
            todo.cmd_add = old_cmd_add
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].category, "Engineering")
        self.assertEqual(calls[0].task, "fixed bug")
        self.assertEqual(calls[0].due, "7d")

    def test_task_due_dispatch_still_accepts_legacy_order(self):
        calls = []
        old_cmd_due = todo.cmd_due
        try:
            def fake_cmd_due(args):
                calls.append(args)
                return 0

            todo.cmd_due = fake_cmd_due
            parser = todo.build_parser()
            rc = todo.cmd_task(parser.parse_args(["task", "--due", "website", "2d"]))
        finally:
            todo.cmd_due = old_cmd_due
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].task, "website")
        self.assertEqual(calls[0].date, "2d")

    def test_task_wait_due_dispatches_to_wait(self):
        calls = []
        old_cmd_wait = todo.cmd_wait
        try:
            def fake_cmd_wait(args):
                calls.append(args)
                return 0

            todo.cmd_wait = fake_cmd_wait
            parser = todo.build_parser()
            rc = todo.cmd_task(parser.parse_args(["task", "--wait", "--due", "7d", "website", "waiting"]))
        finally:
            todo.cmd_wait = old_cmd_wait
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].task, "website")
        self.assertEqual(calls[0].text, "waiting")
        self.assertEqual(calls[0].due, "7d")

    def test_wait_due_clear_is_rejected(self):
        class Cfg:
            wait_days = 2

        with self.assertRaises(todo.TodoError) as cm:
            todo.wait_follow_date(todo.argparse.Namespace(due="clear", after=None), Cfg())
        self.assertIn("Waiting tasks need a follow-up due date", str(cm.exception))

    def test_task_undone_dispatches_to_undone(self):
        calls = []
        old_cmd_undone = todo.cmd_undone
        try:
            def fake_cmd_undone(args):
                calls.append(args)
                return 0

            todo.cmd_undone = fake_cmd_undone
            parser = todo.build_parser()
            rc = todo.cmd_task(parser.parse_args(["task", "--undone", "virtuals2-sca"]))
        finally:
            todo.cmd_undone = old_cmd_undone
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].task, "virtuals2-sca")

    def test_task_delete_dispatches_to_delete(self):
        calls = []
        old_cmd_delete_task = todo.cmd_delete_task
        try:
            def fake_cmd_delete_task(args):
                calls.append(args)
                return 0

            todo.cmd_delete_task = fake_cmd_delete_task
            parser = todo.build_parser()
            rc = todo.cmd_task(parser.parse_args(["task", "--delete", "--yes", "virtuals2-sca"]))
        finally:
            todo.cmd_delete_task = old_cmd_delete_task
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].task, "virtuals2-sca")
        self.assertTrue(calls[0].yes)

    def test_delete_without_yes_requires_interactive_terminal(self):
        with self.assertRaises(todo.TodoError) as cm:
            todo.confirm_delete("task", "website", yes=False)
        self.assertIn("Use --yes to delete non-interactively", str(cm.exception))

    def test_delete_completed_task_reopens_then_deletes(self):
        calls = []
        old_reopen_item = todo.reopen_item
        old_delete_item = todo.delete_item
        try:
            todo.reopen_item = lambda client, cache, task_id: calls.append(("reopen", task_id))
            todo.delete_item = lambda client, cache, task_id: calls.append(("delete", task_id))
            was_done = todo.delete_task_item(None, None, {"id": "task1", "checked": True})
        finally:
            todo.reopen_item = old_reopen_item
            todo.delete_item = old_delete_item
        self.assertTrue(was_done)
        self.assertEqual(calls, [("reopen", "task1"), ("delete", "task1")])

    def test_move_open_task_only_moves(self):
        calls = []
        old_reopen_item = todo.reopen_item
        old_mutate = todo.mutate
        old_close_item = todo.close_item
        try:
            todo.reopen_item = lambda client, cache, task_id: calls.append(("reopen", task_id))
            todo.mutate = lambda client, cache, type_, args: calls.append((type_, args))
            todo.close_item = lambda client, cache, task_id: calls.append(("close", task_id))

            was_done = todo.move_task_to_project(
                None,
                None,
                {"id": "task1", "checked": False},
                {"id": "vm", "name": "Admin"},
            )
        finally:
            todo.reopen_item = old_reopen_item
            todo.mutate = old_mutate
            todo.close_item = old_close_item
        self.assertFalse(was_done)
        self.assertEqual(calls, [("item_move", {"id": "task1", "project_id": "vm"})])

    def test_move_completed_task_reopens_moves_and_closes(self):
        calls = []
        old_reopen_item = todo.reopen_item
        old_mutate = todo.mutate
        old_close_item = todo.close_item
        try:
            todo.reopen_item = lambda client, cache, task_id: calls.append(("reopen", task_id))
            todo.mutate = lambda client, cache, type_, args: calls.append((type_, args))
            todo.close_item = lambda client, cache, task_id: calls.append(("close", task_id))

            was_done = todo.move_task_to_project(
                None,
                None,
                {"id": "task1", "checked": True},
                {"id": "vm", "name": "Admin"},
            )
        finally:
            todo.reopen_item = old_reopen_item
            todo.mutate = old_mutate
            todo.close_item = old_close_item
        self.assertTrue(was_done)
        self.assertEqual(calls, [
            ("reopen", "task1"),
            ("item_move", {"id": "task1", "project_id": "vm"}),
            ("close", "task1"),
        ])

    def test_step_modes_parse(self):
        parser = todo.build_parser()
        self.assertEqual(parser.parse_args(["step", "website"]).values, ["website"])
        self.assertTrue(parser.parse_args(["step", "--refresh", "website"]).refresh)
        add_args = parser.parse_args(["step", "--add", "website", "review", "publish"])
        add_done_args = parser.parse_args(["step", "--add", "--done", "website", "tested", "delivered"])
        new_closed_args = parser.parse_args(["step", "--new", "--closed", "website", "tested", "delivered"])
        add_due_args = parser.parse_args(["step", "--add", "--due", "7d", "website", "review"])
        add_due_after_args = parser.parse_args(["step", "--add", "website", "review", "--due", "7d"])
        done_args = parser.parse_args(["step", "--done", "website", "review"])
        close_args = parser.parse_args(["step", "--close", "website", "review"])
        undone_args = parser.parse_args(["step", "--undone", "website", "review"])
        unclose_args = parser.parse_args(["step", "--unclose", "website", "review"])
        delete_args = parser.parse_args(["step", "--delete", "--yes", "website", "review"])
        self.assertTrue(add_args.add)
        self.assertEqual(add_args.values, ["website", "review", "publish"])
        self.assertTrue(add_done_args.add)
        self.assertTrue(add_done_args.done)
        self.assertEqual(add_done_args.values, ["website", "tested", "delivered"])
        self.assertTrue(new_closed_args.add)
        self.assertTrue(new_closed_args.done)
        self.assertEqual(new_closed_args.values, ["website", "tested", "delivered"])
        self.assertEqual(add_due_args.due, "7d")
        self.assertEqual(add_due_args.values, ["website", "review"])
        self.assertEqual(add_due_after_args.due, "7d")
        self.assertEqual(add_due_after_args.values, ["website", "review"])
        self.assertTrue(done_args.done)
        self.assertEqual(done_args.values, ["website", "review"])
        self.assertTrue(close_args.done)
        self.assertEqual(close_args.values, ["website", "review"])
        self.assertTrue(undone_args.undone)
        self.assertEqual(undone_args.values, ["website", "review"])
        self.assertTrue(unclose_args.undone)
        self.assertEqual(unclose_args.values, ["website", "review"])
        self.assertTrue(delete_args.delete)
        self.assertTrue(delete_args.yes)
        self.assertEqual(delete_args.values, ["website", "review"])

    def test_step_add_due_dispatches_to_step(self):
        calls = []
        old_cmd_step = todo.cmd_step
        try:
            def fake_cmd_step(args):
                calls.append(args)
                return 0

            todo.cmd_step = fake_cmd_step
            parser = todo.build_parser()
            rc = todo.cmd_step_noun(parser.parse_args(["step", "--add", "--due", "7d", "website", "review"]))
        finally:
            todo.cmd_step = old_cmd_step
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].task, "website")
        self.assertEqual(calls[0].steps, ["review"])
        self.assertEqual(calls[0].due, "7d")

    def test_step_due_requires_add_mode(self):
        parser = todo.build_parser()
        with self.assertRaises(todo.TodoError) as cm:
            todo.cmd_step_noun(parser.parse_args(["step", "--due", "7d", "website"]))
        self.assertIn("only with `todo step --add`", str(cm.exception))

    def test_step_refresh_rejected_for_mutation_modes(self):
        parser = todo.build_parser()
        with self.assertRaises(todo.TodoError) as cm:
            todo.cmd_step_noun(parser.parse_args(["step", "--refresh", "--done", "website", "review"]))
        self.assertIn("mutation modes refresh automatically", str(cm.exception))

    def test_step_yes_rejected_for_non_delete_modes(self):
        parser = todo.build_parser()
        with self.assertRaises(todo.TodoError) as cm:
            todo.cmd_step_noun(parser.parse_args(["step", "--yes", "--done", "website", "review"]))
        self.assertIn("Use --yes only", str(cm.exception))

    def test_step_undone_dispatches_to_step_undone(self):
        calls = []
        old_cmd_step_undone = todo.cmd_step_undone
        try:
            def fake_cmd_step_undone(args):
                calls.append(args)
                return 0

            todo.cmd_step_undone = fake_cmd_step_undone
            parser = todo.build_parser()
            rc = todo.cmd_step_noun(parser.parse_args(["step", "--undone", "website", "review"]))
        finally:
            todo.cmd_step_undone = old_cmd_step_undone
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].task, "website")
        self.assertEqual(calls[0].step, "review")

    def test_step_delete_dispatches_to_delete(self):
        calls = []
        old_cmd_delete_step = todo.cmd_delete_step
        try:
            def fake_cmd_delete_step(args):
                calls.append(args)
                return 0

            todo.cmd_delete_step = fake_cmd_delete_step
            parser = todo.build_parser()
            rc = todo.cmd_step_noun(parser.parse_args(["step", "--delete", "--yes", "website", "review"]))
        finally:
            todo.cmd_delete_step = old_cmd_delete_step
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0].task, "website")
        self.assertEqual(calls[0].step, "review")
        self.assertTrue(calls[0].yes)

    def test_delete_completed_step_under_completed_task_preserves_parent_done(self):
        calls = []
        old_reopen_item = todo.reopen_item
        old_delete_item = todo.delete_item
        old_close_item = todo.close_item
        try:
            todo.reopen_item = lambda client, cache, task_id: calls.append(("reopen", task_id))
            todo.delete_item = lambda client, cache, task_id: calls.append(("delete", task_id))
            todo.close_item = lambda client, cache, task_id: calls.append(("close", task_id))
            parent_was_done, step_was_done = todo.delete_step_item(
                None,
                None,
                {"id": "task1", "checked": True},
                {"id": "step1", "checked": True},
            )
        finally:
            todo.reopen_item = old_reopen_item
            todo.delete_item = old_delete_item
            todo.close_item = old_close_item
        self.assertTrue(parent_was_done)
        self.assertTrue(step_was_done)
        self.assertEqual(calls, [
            ("reopen", "task1"),
            ("reopen", "step1"),
            ("delete", "step1"),
            ("close", "task1"),
        ])

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
        self.assertFalse(args.refresh)
        args = parser.parse_args(["comment", "--refresh", "deliver release"])
        self.assertTrue(args.refresh)

    def test_comment_add_flag(self):
        parser = todo.build_parser()
        args = parser.parse_args(["comment", "--add", "deliver release", "one", "two"])
        self.assertTrue(args.add)
        self.assertEqual(args.values, ["deliver release", "one", "two"])

    def test_comment_edit_flag(self):
        parser = todo.build_parser()
        args = parser.parse_args(["comment", "--edit", "deliver release"])
        self.assertEqual(args.values, ["deliver release"])
        self.assertTrue(args.edit)

    def test_search_refresh_flag(self):
        parser = todo.build_parser()
        args = parser.parse_args(["search", "--refresh", "REVIEW-123"])
        self.assertTrue(args.refresh)
        self.assertEqual(args.values, ["REVIEW-123"])

    def test_display_refresh_flags_parse(self):
        parser = todo.build_parser()
        self.assertTrue(parser.parse_args(["now", "--refresh"]).refresh)
        self.assertTrue(parser.parse_args(["waiting", "--refresh"]).refresh)
        self.assertTrue(parser.parse_args(["someday", "--refresh"]).refresh)

    def test_report_refresh_flag_removed(self):
        parser = todo.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["report", "--refresh"])

    def test_comment_refresh_rejected_for_mutation_modes(self):
        parser = todo.build_parser()
        with self.assertRaises(todo.TodoError) as cm:
            todo.cmd_comment_noun(parser.parse_args(["comment", "--refresh", "--add", "website", "note"]))
        self.assertIn("mutation modes refresh automatically", str(cm.exception))

    def test_mapped_id_reads_todoist_temp_mapping(self):
        response = {
            "_todo_temp_id": "tmp1",
            "temp_id_mapping": {"tmp1": "real1"},
        }
        self.assertEqual(todo.mapped_id(response), "real1")

    def test_todoist_get_retries_transient_connection_failure(self):
        client = todo.Todoist("token")
        calls = []
        sleeps = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"ok": true}'

        def fake_urlopen(req, timeout):
            calls.append((req, timeout))
            if len(calls) == 1:
                raise todo.urllib.error.URLError("temporary outage")
            return Response()

        old_urlopen = todo.urllib.request.urlopen
        old_sleep = todo.time.sleep
        try:
            todo.urllib.request.urlopen = fake_urlopen
            todo.time.sleep = lambda seconds: sleeps.append(seconds)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(client.request("GET", f"{todo.API_BASE}/comments"), {"ok": True})
            self.assertEqual(len(calls), 2)
            self.assertEqual(sleeps, [1])
            self.assertIn("todo: warning: Todoist API connection failed: temporary outage", err.getvalue())
        finally:
            todo.urllib.request.urlopen = old_urlopen
            todo.time.sleep = old_sleep

    def test_todoist_unsafe_post_does_not_retry_connection_failure(self):
        client = todo.Todoist("token")
        calls = []

        def fake_urlopen(req, timeout):
            calls.append((req, timeout))
            raise todo.urllib.error.URLError("maybe processed")

        old_urlopen = todo.urllib.request.urlopen
        old_sleep = todo.time.sleep
        try:
            todo.urllib.request.urlopen = fake_urlopen
            todo.time.sleep = lambda seconds: self.fail("unsafe POST should not sleep for retry")
            with self.assertRaises(todo.TodoError):
                client.request("POST", f"{todo.API_BASE}/comments", {"content": "note"})
            self.assertEqual(len(calls), 1)
        finally:
            todo.urllib.request.urlopen = old_urlopen
            todo.time.sleep = old_sleep

    def test_todoist_comment_methods_use_sync_commands(self):
        client = todo.Todoist("token")
        calls = []
        old_command = client.command
        try:
            def fake_command(type_, args):
                calls.append((type_, args))
                return {"sync_status": "ok"}

            client.command = fake_command
            client.add_comment("task1", "new comment")
            client.update_comment("note1", "updated comment")
            client.delete_comment("note2")
        finally:
            client.command = old_command
        self.assertEqual(calls, [
            ("note_add", {"item_id": "task1", "content": "new comment"}),
            ("note_update", {"id": "note1", "content": "updated comment"}),
            ("note_delete", {"id": "note2"}),
        ])

    def test_find_added_task_id(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["items"] = [{
            "id": "task1",
            "project_id": "gate",
            "content": "Deliver next release",
        }]
        self.assertEqual(todo.find_added_task_id(cache, "gate", "Deliver next release"), "task1")

    def test_find_added_step_id(self):
        cache = todo.Cache(todo.Cache.empty())
        cache.data["items"] = [
            {"id": "task1", "project_id": "gate", "content": "Deliver next release"},
            {"id": "step1", "project_id": "gate", "parent_id": "task1", "content": "tested"},
        ]
        self.assertEqual(todo.find_added_step_id(cache, "task1", "tested"), "step1")


if __name__ == "__main__":
    unittest.main()
