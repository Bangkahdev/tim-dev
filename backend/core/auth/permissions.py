from core.rbac import has_permission

def require(role, permission):
    if not has_permission(role, permission):
        raise PermissionError(permission)
