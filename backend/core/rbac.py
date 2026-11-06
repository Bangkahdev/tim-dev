"""Role-based access control for Bangkah backend."""

ROLES = {
    "owner": {"*"},
    "admin": {"domain.read", "domain.write", "infra.read", "infra.write", "ftp.read", "ftp.write", "mail.read", "mail.write", "network.read", "network.write"},
    "employee": {"domain.read", "ftp.read", "mail.read", "network.read"},
}

def has_permission(role, permission):
    perms = ROLES.get(role, set())
    return "*" in perms or permission in perms
