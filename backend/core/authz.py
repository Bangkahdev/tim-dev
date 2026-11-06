"""HTTP route authorization for the Bangkah office API."""

from core.rbac import has_permission

SELF_SERVICE = {"/api/auth/logout", "/api/auth/me"}
READ_METHODS = {"GET", "HEAD", "OPTIONS"}

_EXACT = {
    "/api/status": ("company.read", "company.read"),
    "/api/departments": ("company.read", "company.read"),
    "/api/employees": ("company.read", "company.read"),
    "/api/projects": ("company.read", "company.read"),
    "/api/usage": ("company.read", "company.read"),
    "/api/office/state": ("company.read", "company.read"),
    "/api/office/activity": ("company.read", "company.read"),
    "/api/office/player": ("company.read", "office.write"),
    "/api/office/action": ("company.read", "office.write"),
    "/api/office/activity/tick": ("company.read", "office.write"),
    "/api/chat/history": ("chat.read", "chat.read"),
    "/api/room-chat": ("chat.team", "chat.team"),
    "/api/employee-chat": ("chat.employee", "chat.employee"),
    "/api/chat": ("project.run", "project.run"),
    "/api/command": ("project.run", "project.run"),
    "/api/audit": ("audit.read", "audit.read"),
    "/api/events": ("audit.read", "audit.read"),
    "/api/knowledge/documents": ("knowledge.read", "knowledge.write"),
    "/api/knowledge/search": ("knowledge.read", "knowledge.read"),
    "/api/print-jobs": ("print.read", "print.create"),
    "/api/approvals": ("approval.read", "approval.create"),
    "/api/outbox": ("outbox.read", "outbox.execute"),
    "/api/outbox/retry-due": ("outbox.read", "outbox.execute"),
    "/api/tasks": ("company.read", "task.write"),
    "/api/meetings": ("company.read", "meeting.write"),
    "/api/papers": ("company.read", "paper.create"),
    "/api/workstations": ("desktop.read", "desktop.write"),
    "/api/domain/state": ("domain.read", "domain.read"),
    "/api/domain/join": ("domain.read", "domain.write"),
    "/api/domain/dns/lookup": ("domain.read", "domain.read"),
    "/api/domain/dns/records": ("domain.read", "domain.read"),
    "/api/domain/dns/record": ("domain.read", "domain.write"),
    "/api/infra/services": ("infra.read", "infra.read"),
    "/api/infra/service/start": ("infra.read", "infra.write"),
    "/api/infra/service/stop": ("infra.read", "infra.write"),
    "/api/ftp/status": ("ftp.read", "ftp.read"),
    "/api/ftp/provision": ("ftp.read", "ftp.write"),
    "/api/mail/status": ("mail.read", "mail.read"),
    "/api/mail/provision": ("mail.read", "mail.write"),
    "/api/network/networks": ("network.read", "network.read"),
    "/api/network/subnets": ("network.read", "network.read"),
    "/api/network/scopes": ("network.read", "network.read"),
    "/api/network/leases": ("network.read", "network.read"),
    "/api/network/vpn/peers": ("network.read", "network.read"),
    "/api/network/subnet": ("network.read", "network.write"),
    "/api/network/scope": ("network.read", "network.write"),
    "/api/network/lease": ("network.read", "network.write"),
    "/api/network/vpn/peer": ("network.read", "network.write"),
    "/api/terminal/exec": ("desktop.write", "desktop.write"),
    "/api/desktop/session": ("desktop.read", "desktop.read"),
    "/api/desktop/session/close": ("desktop.session", "desktop.session"),
    "/api/desktop/system": ("desktop.read", "desktop.read"),
    "/api/desktop/files": ("desktop.read", "desktop.read"),
    "/api/desktop/files/content": ("desktop.read", "desktop.read"),
    "/api/desktop/files/write": ("desktop.write", "desktop.write"),
    "/api/desktop/audit": ("desktop.read", "desktop.read"),
}

_SUFFIX = (
    ("/api/tasks/", "/transition", "task.transition"),
    ("/api/meetings/", None, "meeting.write"),
    ("/api/papers/", "/review", "paper.review"),
    ("/api/approvals/", "/approve", "approval.decide"),
    ("/api/approvals/", "/reject", "approval.decide"),
    ("/api/outbox/", "/execute", "outbox.execute"),
    ("/api/outbox/", "/reconcile", "outbox.reconcile"),
    ("/api/outbox/", "/requeue", "outbox.requeue"),
    ("/api/print-jobs/", None, "print.read"),
    ("/api/workstations/", "/login", "desktop.session"),
    ("/api/workstations/", None, "desktop.read"),
    ("/api/papers/", None, "company.read"),
)


def _clean(route):
    route = str(route or "/").split("?")[0]
    if len(route) > 1:
        route = route.rstrip("/")
    return route


def required_permission(route, method):
    route = _clean(route)
    if route in SELF_SERVICE or route == "/api/auth/login":
        return None
    read = str(method or "GET").upper() in READ_METHODS

    if route in _EXACT:
        read_permission, write_permission = _EXACT[route]
        return read_permission if read else write_permission

    for prefix, suffix, permission in _SUFFIX:
        if route.startswith(prefix) and (suffix is None or route.endswith(suffix)):
            return permission

    for prefix, read_permission, write_permission in (
        ("/api/domain/", "domain.read", "domain.write"),
        ("/api/infra/", "infra.read", "infra.write"),
        ("/api/ftp/", "ftp.read", "ftp.write"),
        ("/api/mail/", "mail.read", "mail.write"),
        ("/api/network/", "network.read", "network.write"),
        ("/api/desktop/", "desktop.read", "desktop.write"),
    ):
        if route.startswith(prefix):
            return read_permission if read else write_permission

    return "__unknown_route__"


def is_allowed(role, route, method):
    permission = required_permission(route, method)
    if permission is None:
        return True
    if permission == "__unknown_route__":
        return False
    return has_permission(role, permission)
