"""HTTP integration tests for authentication, RBAC, actor identity and routing."""

import http.client
import json
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer

import office_server as server
from core.auth import sessions
from core.office_store import LOCK, STORE


class ApiAuthIntegrationTests(unittest.TestCase):
    PORT = None
    HTTPD = None
    SUFFIX = uuid.uuid4().hex[:6]
    PASSWORD = "integration-password-123"

    @classmethod
    def setUpClass(cls):
        cls.HTTPD = ThreadingHTTPServer(("127.0.0.1", 0), server.OfficeHandler)
        cls.PORT = cls.HTTPD.server_address[1]
        threading.Thread(target=cls.HTTPD.serve_forever, daemon=True).start()

        cls.users = {
            "owner": f"it.owner.{cls.SUFFIX}",
            "secretary": f"it.secretary.{cls.SUFFIX}",
            "manager": f"it.manager.{cls.SUFFIX}",
            "employee": f"it.employee.{cls.SUFFIX}",
            "disabled": f"it.disabled.{cls.SUFFIX}",
        }
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM auth_sessions WHERE username LIKE ?", (f"%{cls.SUFFIX}%",))
            db.execute("DELETE FROM auth_users WHERE username LIKE ?", (f"%{cls.SUFFIX}%",))

        sessions.create_user(cls.users["owner"], cls.PASSWORD, "owner",
                             department_id="executive")
        sessions.create_user(cls.users["secretary"], cls.PASSWORD, "secretary",
                             employee_id="coo", department_id="operations")
        sessions.create_user(cls.users["manager"], cls.PASSWORD, "manager",
                             employee_id="lead", department_id="executive")
        sessions.create_user(cls.users["employee"], cls.PASSWORD, "employee",
                             employee_id="backend", department_id="engineering")
        sessions.create_user(cls.users["disabled"], cls.PASSWORD, "employee",
                             employee_id="qa", department_id="engineering", enabled=False)

    @classmethod
    def tearDownClass(cls):
        cls.HTTPD.shutdown()
        cls.HTTPD.server_close()
        with LOCK, STORE._db() as db:
            db.execute("UPDATE domain_state SET internal_dns_managed=0, joined_at=NULL")
            db.execute("DELETE FROM domain_computers WHERE workstation_id='PC-BE-001'")
            db.execute("DELETE FROM dns_records WHERE name LIKE ?", (f"route{cls.SUFFIX}%",))
            db.execute("DELETE FROM auth_sessions WHERE username LIKE ?", (f"%{cls.SUFFIX}%",))
            db.execute("DELETE FROM auth_users WHERE username LIKE ?", (f"%{cls.SUFFIX}%",))

    def request(self, method, path, body=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.PORT, timeout=15)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        payload = json.dumps(body) if body is not None else None
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw.decode("utf-8", "replace")}
        return response.status, data

    def setUp(self):
        sessions.clear_login_throttle()

    def login(self, role):
        status, data = self.request("POST", "/api/auth/login", {
            "username": self.users[role], "password": self.PASSWORD})
        self.assertEqual(status, 200, data)
        return data["session"]["token"]

    # --- authentication ---

    def test_anonymous_requests_are_401(self):
        self.assertEqual(self.request("GET", "/api/departments")[0], 401)
        self.assertEqual(self.request("GET", "/api/status")[0], 401)
        self.assertEqual(self.request("POST", "/api/tasks", {"title": "x"})[0], 401)
        self.assertEqual(self.request("POST", "/api/domain/join",
                                      {"workstation_id": "PC-BE-001"})[0], 401)

    def test_invalid_token_is_401(self):
        self.assertEqual(self.request("GET", "/api/departments", token="not-a-session")[0], 401)

    def test_expired_session_is_401(self):
        token = sessions.create_session(self.users["employee"], ttl_seconds=-60)
        self.assertEqual(self.request("GET", "/api/departments", token=token)[0], 401)

    def test_revoked_and_disabled_accounts_are_401(self):
        token = self.login("employee")
        self.assertEqual(self.request("GET", "/api/departments", token=token)[0], 200)
        self.assertEqual(self.request("POST", "/api/auth/logout", {}, token=token)[0], 200)
        self.assertEqual(self.request("GET", "/api/departments", token=token)[0], 401)

        status, _ = self.request("POST", "/api/auth/login", {
            "username": self.users["disabled"], "password": self.PASSWORD})
        self.assertEqual(status, 401)

    def test_login_me_and_logout_flow(self):
        token = self.login("owner")
        status, data = self.request("GET", "/api/auth/me", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["user"]["username"], self.users["owner"])
        self.assertEqual(data["user"]["role"], "owner")
        self.assertEqual(self.request("POST", "/api/auth/logout", {}, token=token)[0], 200)
        self.assertEqual(self.request("GET", "/api/auth/me", token=token)[0], 401)

    def test_legacy_shared_token_is_not_an_identity_by_default(self):
        old_token, old_role = server.API_AUTH_TOKEN, server.LEGACY_TOKEN_ROLE
        server.API_AUTH_TOKEN, server.LEGACY_TOKEN_ROLE = "legacy-secret-value", ""
        try:
            self.assertEqual(self.request("GET", "/api/departments",
                                          token="legacy-secret-value")[0], 401)
            server.LEGACY_TOKEN_ROLE = "owner"
            status, data = self.request("GET", "/api/departments", token="legacy-secret-value")
            self.assertEqual(status, 200, data)
            _, me = self.request("GET", "/api/auth/me", token="legacy-secret-value")
            self.assertEqual(me["user"]["username"], "legacy-token")
            self.assertEqual(me["user"]["role"], "owner")
        finally:
            server.API_AUTH_TOKEN, server.LEGACY_TOKEN_ROLE = old_token, old_role

    # --- RBAC and scope ---

    def test_owner_has_full_access(self):
        token = self.login("owner")
        self.assertEqual(self.request("GET", "/api/departments", token=token)[0], 200)
        self.assertEqual(self.request("GET", "/api/audit", token=token)[0], 200)
        self.assertEqual(self.request("GET", "/api/outbox", token=token)[0], 200)
        self.assertEqual(self.request("POST", "/api/domain/join",
                                      {"workstation_id": "PC-BE-001"}, token=token)[0], 201)

    def test_secretary_can_coordinate_but_not_engineering_or_infra(self):
        token = self.login("secretary")
        self.assertEqual(self.request("GET", "/api/audit", token=token)[0], 200)
        status, data = self.request("POST", "/api/tasks", {
            "title": f"Secretary scoped task {self.SUFFIX}", "assignee_id": "coo"}, token=token)
        self.assertEqual(status, 201, data)
        status, _ = self.request("POST", "/api/tasks", {
            "title": "Secretary out of scope", "assignee_id": "backend"}, token=token)
        self.assertEqual(status, 403)
        self.assertEqual(self.request("POST", "/api/domain/join",
                                      {"workstation_id": "PC-BE-001"}, token=token)[0], 403)
        self.assertEqual(self.request("POST", "/api/approvals", {
            "action_type": "expense.purchase", "summary": "x",
            "payload": {"vendor": "V", "amount": 1, "currency": "IDR"}}, token=token)[0], 201)

    def test_manager_can_manage_engineering_but_not_external_writes(self):
        token = self.login("manager")
        status, data = self.request("POST", "/api/tasks", {
            "title": f"Manager task {self.SUFFIX}", "assignee_id": "backend"}, token=token)
        self.assertEqual(status, 201, data)
        self.assertEqual(self.request("GET", "/api/outbox", token=token)[0], 200)
        self.assertEqual(self.request("POST", "/api/domain/dns/record", {
            "name": f"mgr{self.SUFFIX}", "type": "A", "value": "10.1.2.3"},
            token=token)[0], 403)

    def test_employee_is_scoped_to_own_department_and_tasks(self):
        employee_token = self.login("employee")
        manager_token = self.login("manager")
        _, backend_task = self.request("POST", "/api/tasks", {
            "title": f"Employee task {self.SUFFIX}", "assignee_id": "backend"},
            token=manager_token)
        _, other_task = self.request("POST", "/api/tasks", {
            "title": f"Other department {self.SUFFIX}", "assignee_id": "coo"},
            token=manager_token)

        status, data = self.request("GET", "/api/employees", token=employee_token)
        self.assertEqual(status, 200)
        self.assertEqual([row["id"] for row in data["employees"]], ["backend"])

        status, data = self.request("GET", "/api/tasks", token=employee_token)
        self.assertEqual(status, 200)
        self.assertTrue(all(row.get("assignee_id") == "backend" for row in data["tasks"]))

        self.assertEqual(self.request("GET", "/api/audit", token=employee_token)[0], 403)
        self.assertEqual(self.request("GET", "/api/outbox", token=employee_token)[0], 403)
        self.assertEqual(self.request("POST", "/api/tasks", {
            "title": "Employee cannot create"}, token=employee_token)[0], 403)

        status, _ = self.request("POST", f"/api/tasks/{other_task['task']['id']}/transition",
                                 {"status": "in_progress"}, token=employee_token)
        self.assertEqual(status, 403)

        status, _ = self.request("POST", f"/api/tasks/{backend_task['task']['id']}/transition",
                                 {"status": "in_progress"}, token=employee_token)
        self.assertEqual(status, 200)

    def test_approval_decision_is_owner_only_and_reviewer_is_recorded(self):
        manager_token = self.login("manager")
        owner_token = self.login("owner")
        status, data = self.request("POST", "/api/approvals", {
            "action_type": "expense.purchase", "summary": f"Approval {self.SUFFIX}",
            "payload": {"vendor": "Vendor", "amount": 250, "currency": "IDR"}},
            token=manager_token)
        self.assertEqual(status, 201, data)
        approval_id = data["approval"]["id"]
        self.assertEqual(data["approval"]["created_by"], self.users["manager"])

        status, _ = self.request("POST", f"/api/approvals/{approval_id}/approve",
                                 {"note": "not mine"}, token=manager_token)
        self.assertEqual(status, 403)

        status, data = self.request("POST", f"/api/approvals/{approval_id}/approve",
                                    {"note": "approved"}, token=owner_token)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["approval"]["reviewer"], self.users["owner"])

    def test_actor_cannot_be_spoofed_through_request_body(self):
        manager_token = self.login("manager")
        owner_token = self.login("owner")
        status, data = self.request("POST", "/api/tasks", {
            "title": f"Spoof task {self.SUFFIX}", "assignee_id": "backend",
            "actor": self.users["owner"]}, token=manager_token)
        self.assertEqual(status, 201, data)
        task_id = data["task"]["id"]

        status, audit = self.request("GET", "/api/audit?limit=200", token=owner_token)
        self.assertEqual(status, 200)
        created = [event for event in audit["events"]
                   if event["event_type"] == "task_created" and event["entity_id"] == task_id]
        self.assertTrue(created)
        self.assertEqual(created[0]["actor"], self.users["manager"])
        self.assertNotEqual(created[0]["actor"], self.users["owner"])

    # --- routing ---

    def test_domain_join_and_dns_record_routes_reach_handlers(self):
        token = self.login("owner")
        status, data = self.request("POST", "/api/domain/join",
                                    {"workstation_id": "PC-BE-001"}, token=token)
        self.assertEqual(status, 201, data)
        self.assertEqual(data["domain"]["status"], "joined")

        name = f"route{self.SUFFIX}"
        status, data = self.request("POST", "/api/domain/dns/record", {
            "name": name, "type": "A", "value": "10.9.8.7"}, token=token)
        self.assertEqual(status, 201, data)
        self.assertEqual(data["record"]["name"], name)

        status, data = self.request("GET", f"/api/domain/dns/lookup?name={name}", token=token)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["found"])
        self.assertEqual(data["record"]["value"], "10.9.8.7")



    def test_login_throttle_returns_429_with_retry_after_and_generic_message(self):
        sessions.clear_login_throttle()
        target = self.users["employee"]
        status = 0
        data = {}
        headers = {}
        for _ in range(6):
            connection = http.client.HTTPConnection("127.0.0.1", self.PORT, timeout=15)
            payload = json.dumps({"username": target, "password": "wrong-password"})
            connection.request("POST", "/api/auth/login", payload, {"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read()
            headers = {k: v for k, v in response.getheaders()}
            status = response.status
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {}
            connection.close()
        self.assertEqual(status, 429, data)
        self.assertIn("Retry-After", headers)
        self.assertEqual(data.get("error", {}).get("code"), "TOO_MANY_ATTEMPTS")
        self.assertEqual(data.get("error", {}).get("message"), "Login failed")
        sessions.clear_login_throttle()

    def test_nonexistent_user_returns_same_generic_invalid_credentials(self):
        sessions.clear_login_throttle()
        status, data = self.request("POST", "/api/auth/login", {
            "username": "nobody." + self.SUFFIX, "password": "wrong-password"})
        self.assertEqual(status, 401, data)
        self.assertEqual(data.get("error", {}).get("code"), "INVALID_CREDENTIALS")
        self.assertEqual(data.get("error", {}).get("message"), "Login failed")


if __name__ == "__main__":
    unittest.main()
