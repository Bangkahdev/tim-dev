from core.auth.sessions import verify_user, create_session, revoke_session, get_session

def login(username, password):
    user = verify_user(username, password)
    if not user:
        return None
    token = create_session(user["username"])
    return {"token": token, "username": user["username"], "role": user["role"]}

def logout(token):
    revoke_session(token)

def current_user(token):
    return get_session(token)
