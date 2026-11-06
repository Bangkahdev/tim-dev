"""Route-based authorization (default deny)."""

ROUTE_PERMISSIONS = {
    "/api/terminal/exec": "owner",
    "/api/desktop/files/write": "owner",
    "/api/infra/service/start": "owner",
    "/api/infra/service/stop": "owner",
    "/api/network/subnet": "owner",
    "/api/network/scope": "owner",
    "/api/network/lease": "owner",
    "/api/network/vpn/peer": "owner",
    "/api/domain/dns/record": "admin",
    "/api/domain/join": "admin",
    "/api/ftp/provision": "admin",
    "/api/mail/provision": "admin",
}

def allowed(role, route):
    # owner can do everything
    if role == "owner":
        return True
    # admin for infra/domain/ftp/mail/network
    if role == "admin":
        if route.startswith("/api/infra") or route.startswith("/api/domain") or route.startswith("/api/ftp") or route.startswith("/api/mail") or route.startswith("/api/network"):
            return True
        return False
    # employee read-only (GET allowed elsewhere)
    return False

def check(role, route):
    if not allowed(role, route):
        raise PermissionError("Forbidden")
