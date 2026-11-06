# Security Assessment

- Bearer token via BANGKAH_API_TOKEN enforced in office_server (optional).
- RBAC helper in core/rbac.py (roles: owner/admin/employee).
- Permission enforcement on endpoints: partial; needs consistent integration.
- Secrets stored in .env (not committed).
