"""Role-based access control and department scope for Bangkah.

Roles follow the company structure: owner, secretary, manager, employee.
``admin`` is retained as a legacy operations role so existing installations
keep working; it never receives owner-only permissions.
"""

READ_SERVICES = {"domain.read", "infra.read", "ftp.read", "mail.read", "network.read"}

COMPANY_READ = {
    "company.read",
    "knowledge.read",
    "chat.read",
    "chat.team",
    "chat.employee",
    "desktop.read",
    "desktop.session",
    "print.read",
} | READ_SERVICES

MANAGER = COMPANY_READ | {
    "task.write",
    "task.assign",
    "task.transition",
    "meeting.write",
    "paper.create",
    "paper.review",
    "approval.create",
    "approval.read",
    "outbox.read",
    "print.create",
    "project.create",
    "project.run",
    "knowledge.write",
    "office.write",
    "audit.read",
    "desktop.write",
}

SECRETARY = COMPANY_READ | {
    "task.write",
    "task.assign",
    "task.transition",
    "meeting.write",
    "paper.create",
    "paper.review",
    "approval.create",
    "approval.read",
    "outbox.read",
    "print.create",
    "knowledge.write",
    "office.write",
    "audit.read",
    "desktop.write",
}

EMPLOYEE = COMPANY_READ | {"task.transition"}

ADMIN = MANAGER | {
    "domain.write",
    "infra.write",
    "ftp.write",
    "mail.write",
    "network.write",
}

ROLES = {
    "owner": {"*"},
    "secretary": SECRETARY,
    "manager": MANAGER,
    "employee": EMPLOYEE,
    "admin": ADMIN,
}

# ``None`` means "the actor's own department"; ``"*"`` means every department.
ROLE_DEPARTMENT_SCOPE = {
    "owner": "*",
    "admin": "*",
    "manager": {"executive", "operations", "engineering", "front_office", "promotion"},
    "secretary": {"executive", "operations", "front_office", "promotion"},
    "employee": None,
}

# Permissions that act on a whole department rather than one owned resource.
SCOPED_PERMISSIONS = {
    "task.write",
    "task.assign",
    "task.transition",
    "meeting.write",
    "paper.create",
    "paper.review",
    "office.write",
}


def has_permission(role, permission):
    perms = ROLES.get(role, set())
    return "*" in perms or permission in perms


def department_scope(role):
    return ROLE_DEPARTMENT_SCOPE.get(role, set())


def can_access_department(role, actor_department, target_department):
    if not target_department:
        return False
    scope = department_scope(role)
    if scope == "*":
        return True
    if scope is None:
        return bool(actor_department) and actor_department == target_department
    return target_department in scope


def can_transition_task(user, task, employees_by_id):
    role = user.get("role")
    if has_permission(role, "task.assign"):
        assignee = employees_by_id.get(task.get("assignee_id") or "", {})
        target_department = assignee.get("department_id")
        return target_department is None or can_access_department(
            role, user.get("department_id"), target_department)
    if has_permission(role, "task.transition"):
        employee_id = user.get("employee_id")
        return bool(employee_id) and task.get("assignee_id") == employee_id
    return False


def can_access_employee(user, target_employee):
    role = user.get("role")
    if has_permission(role, "audit.read"):
        return can_access_department(role, user.get("department_id"),
                                     target_employee.get("department_id"))
    return target_employee.get("id") == user.get("employee_id")


def can_assign(user, assignee, employees_by_id):
    if not has_permission(user.get("role"), "task.assign"):
        return False
    if has_permission(user.get("role"), "*") or user.get("role") == "admin":
        return True
    target_department = (employees_by_id.get(assignee) or {}).get("department_id")
    return can_access_department(user.get("role"), user.get("department_id"), target_department)
