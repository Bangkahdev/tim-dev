
import re


class TaskRouter:

    AGENT_KEYWORDS = {
        "backend": [
            "backend", "server", "database",
            "sql", "authentication", "login",
            "python", "fastapi", "django",
            "flask", "model", "migration"
        ],

        "api": [
            "api", "endpoint", "route",
            "routing", "middleware", "request",
            "response", "rest", "http"
        ],

        "frontend": [
            "frontend", "html", "css",
            "javascript", "react", "vue",
            "component", "button", "layout",
            "responsive", "interface", "ui"
        ],

        "architect": [
            "architecture", "struktur",
            "design", "dependency",
            "integration", "konfigurasi"
        ],

        "qa": [
            "test", "testing", "pytest",
            "validation", "coverage"
        ]
    }

    def __init__(self, agents):
        self.agents = agents

    def classify(self, issue):

        text = issue.lower()

        scores = {}

        for agent, keywords in self.AGENT_KEYWORDS.items():

            scores[agent] = sum(
                1 for keyword in keywords
                if re.search(
                    r"\b" + re.escape(keyword) + r"\b",
                    text
                )
            )

        best_agent = max(
            scores,
            key=scores.get
        )

        if scores[best_agent] == 0:
            best_agent = "backend"

        return {
            "agent": best_agent,
            "score": scores[best_agent],
            "scores": scores
        }

    def get_agent(self, issue):

        result = self.classify(issue)

        return (
            self.agents[result["agent"]],
            result
        )
