from core.auth.sessions import verify_user, create_session, revoke_session, get_session, LoginThrottled

__all__ = ["login", "logout", "current_user", "LoginThrottled"]

def login(username, password, client_ip=None, clock=None, xff_present=None):
    user = verify_user(username, password, client_ip=client_ip, clock=clock, xff_present=xff_present)
    if not user:
        return None
    token = create_session(user["username"])
    return {"token": token, "username": user["username"], "role": user["role"]}

def logout(token):
    revoke_session(token)

def current_user(token):
    return get_session(token)
