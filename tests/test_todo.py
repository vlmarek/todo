import datetime as dt
import importlib.util
import importlib.machinery
import pathlib
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


if __name__ == "__main__":
    unittest.main()
