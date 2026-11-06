from core.rbac import has_permission

ROUTE_PERMISSIONS = [
    ("/api/domain/", "domain.read", "domain.write"),
    ("/api/infra/", "infra.read", "infra.write"),
    ("/api/ftp/", "ftp.read", "ftp.write"),
    ("/api/mail/", "mail.read", "mail.write"),
    ("/api/network/", "network.read", "network.write"),
]
SELF_SERVICE = {"/api/auth/logout", "/api/auth/me"}
READ_METHODS = {"GET", "HEAD"}


def is_allowed(role, route, method):
    if route in SELF_SERVICE:
        return True
    for prefix, read, write in ROUTE_PERMISSIONS:
        if route.startswith(prefix):
            return has_permission(role, read if method.upper() in READ_METHODS else write)
    return has_permission(role, "*")  # selain itu hanya owner
