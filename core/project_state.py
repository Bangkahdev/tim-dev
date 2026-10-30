
import json
import threading
from pathlib import Path
from datetime import datetime


class ProjectState:

    def __init__(self, project_dir):
        self.project_dir = Path(project_dir)
        self.state_dir = self.project_dir / ".factory"
        self.state_file = self.state_dir / "state.json"
        self.lock = threading.RLock()

        self.state_dir.mkdir(parents=True, exist_ok=True)

        if self.state_file.exists():
            self.data = json.loads(
                self.state_file.read_text(encoding="utf-8")
            )
        else:
            self.data = {
                "project": self.project_dir.name,
                "status": "created",
                "owner_command": "",
                "current_phase": "initialization",
                "agents": {},
                "history": [],
                "repair_rounds": 0,
                "qa_status": "pending",
                "last_report": None,
                "created_at": self.now(),
                "updated_at": self.now()
            }
            self.save()

    @staticmethod
    def now():
        return datetime.now().isoformat(timespec="seconds")

    def save(self):
        with self.lock:
            self.data["updated_at"] = self.now()

            temp_file = self.state_file.with_suffix(".tmp")

            temp_file.write_text(
                json.dumps(
                    self.data,
                    indent=2,
                    ensure_ascii=False
                ),
                encoding="utf-8"
            )

            temp_file.replace(self.state_file)

    def update(self, **kwargs):
        with self.lock:
            self.data.update(kwargs)
            self.save()

    def set_agent(self, agent, status, detail=""):
        with self.lock:
            self.data["agents"][agent] = {
                "status": status,
                "detail": detail,
                "updated_at": self.now()
            }
            self.save()

    def add_history(self, actor, action, detail=""):
        with self.lock:
            self.data["history"].append({
                "time": self.now(),
                "actor": actor,
                "action": action,
                "detail": detail
            })
            self.save()

    def increment_repair(self):
        with self.lock:
            self.data["repair_rounds"] += 1
            self.save()
            return self.data["repair_rounds"]

    def set_qa(self, status, detail=""):
        self.update(
            qa_status=status,
            qa_detail=detail
        )

    def get_snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.data))
