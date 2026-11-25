ROLES = {
    "viewer": {"check_balance"},
    "teller": {"check_balance", "update_profile"},
    "customer": {"check_balance", "update_profile", "transfer_money"},
    "admin": {"check_balance", "update_profile", "transfer_money",
          "access_records", "reset_password", "unlock_door"},
}


def allowed(role, action):
    return action in ROLES.get(role, set())