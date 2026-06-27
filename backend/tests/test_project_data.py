from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import database
from routers import projects, schemes
from services.project_welcome import PROJECT_WELCOME_MESSAGE


class ProjectDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        self.user_id = "test-user"
        self.other_user_id = "other-user"
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()
        with database.get_connection() as conn:
            conn.execute(
                "INSERT INTO users (id, seed_project_created) VALUES (?, 1)",
                (self.user_id,),
            )
            conn.execute(
                "INSERT INTO projects (id, user_id, name) VALUES ('project-1', ?, 'Test project')",
                (self.user_id,),
            )
            conn.execute("INSERT INTO project_info (project_id) VALUES ('project-1')")
            conn.execute(
                """
                INSERT INTO schemes
                (id, project_id, scheme_name, scheme_label, strategy)
                VALUES ('scheme-1', 'project-1', 'Test scheme', 'A', 'balanced')
                """
            )
            conn.execute("INSERT INTO scheme_params (scheme_id) VALUES ('scheme-1')")
            conn.execute("INSERT INTO scheme_performance (scheme_id) VALUES ('scheme-1')")
            conn.execute("INSERT INTO teaching_feedback (scheme_id) VALUES ('scheme-1')")

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    @patch("routers.projects.respond_to_project_chat", return_value="This is project advice.")
    def test_chat_messages_are_persisted(self, _respond):
        result = projects.chat_with_project(
            "project-1",
            projects.ChatRequest(message="This is a west-facing office project."),
            user_id=self.user_id,
        )

        self.assertEqual(result["assistant_message"]["content"], "This is project advice.")
        saved = projects.list_project_messages("project-1", user_id=self.user_id)["messages"]
        self.assertEqual([item["role"] for item in saved], ["user", "assistant"])

    def test_delete_scheme_keeps_project(self):
        response = schemes.delete_scheme("scheme-1", user_id=self.user_id)

        self.assertEqual(response.status_code, 204)
        with database.get_connection() as conn:
            self.assertIsNotNone(conn.execute("SELECT id FROM projects").fetchone())
            self.assertIsNone(conn.execute("SELECT id FROM schemes").fetchone())
            self.assertIsNone(conn.execute("SELECT scheme_id FROM scheme_params").fetchone())

    def test_new_project_starts_with_facadegpt_introduction(self):
        created = projects.create_project(projects.ProjectCreate(name="New project"), user_id=self.user_id)

        saved = projects.list_project_messages(created["project_id"], user_id=self.user_id)["messages"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["role"], "assistant")
        self.assertEqual(saved[0]["content"], PROJECT_WELCOME_MESSAGE)

    def test_project_list_is_scoped_by_user(self):
        with database.get_connection() as conn:
            conn.execute(
                "INSERT INTO users (id, seed_project_created) VALUES (?, 1)",
                (self.other_user_id,),
            )
            conn.execute(
                "INSERT INTO projects (id, user_id, name) VALUES ('project-other', ?, 'Other project')",
                (self.other_user_id,),
            )

        listed = projects.list_projects(user_id=self.user_id)["projects"]

        self.assertEqual([item["project_id"] for item in listed], ["project-1"])

    def test_other_user_cannot_read_project(self):
        with self.assertRaises(HTTPException) as raised:
            projects.get_project("project-1", user_id=self.other_user_id)

        self.assertEqual(raised.exception.status_code, 404)

    def test_new_users_receive_separate_seed_projects(self):
        first = projects.list_projects(user_id="new-user-a")["projects"]
        second = projects.list_projects(user_id="new-user-b")["projects"]

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0]["name"], projects.EXAMPLE_PROJECT_NAME)
        self.assertEqual(second[0]["name"], projects.EXAMPLE_PROJECT_NAME)
        self.assertNotEqual(first[0]["project_id"], second[0]["project_id"])


if __name__ == "__main__":
    unittest.main()
