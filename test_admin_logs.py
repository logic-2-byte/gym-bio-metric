import sys

# Mock ZKTeco ADMS USERINFO upload payload
# Columns: PIN\tName\tPassword\tCardNo\tPrivilege\tGroup\tTimeZone\tPIN2
MOCK_USERINFO_PAYLOAD = """
1001\tNormal User 1\t\t\t0\t1\t1\t1001
9999\tAdmin User\t123456\t\t14\t1\t1\t9999
111\tARULAJAY\t\t\t14\t1\t1\t111
1002\tNormal User 2\t\t\t0\t1\t1\t1002
8888\tDevice Manager\t\t\t2\t1\t1\t8888
"""

# Mock ZKTeco ADMS OPLOG (Operation Log) payload
# OPLOG records actions performed on the device menu (enrollment, settings, deletes)
# Only user IDs under an Administrator role can log operational events.
# Columns: OperatorPin\tOPType\tTime\tParam1\tParam2\tParam3\tParam4
MOCK_OPLOG_PAYLOAD = """
9999\t0\t2026-06-07 17:15:30\t1003\t0\t0\t0
111\t1\t2026-06-07 17:20:00\t111\t0\t0\t0
8888\t3\t2026-06-07 17:18:12\t1001\t0\t0\t0
"""


def parse_userinfo(payload: str):
    """
    Parses USERINFO lines and identifies administrators.
    ZKTeco Privileges:
      0: Normal User
      14: Super Admin
      2: Registrar / Manager
    """
    print("\n" + "="*60)
    print("  PARSING USERINFO DATA (IDENTIFYING ADMIN ROLES)")
    print("="*60)
    
    admin_ids = []
    lines = payload.strip().split("\n")
    for line in lines:
        parts = line.strip().split("\t")
        if len(parts) < 5:
            continue
        
        pin = parts[0]
        name = parts[1]
        privilege_str = parts[4]
        
        try:
            privilege = int(privilege_str)
        except ValueError:
            privilege = 0
            
        role = "Normal User"
        is_admin = False
        
        if privilege == 14:
            role = "Super Admin (Admin Role)"
            is_admin = True
        elif privilege == 2:
            role = "Registrar/Manager (Admin Role)"
            is_admin = True
        elif privilege > 0:
            role = f"Admin (Privilege {privilege})"
            is_admin = True
            
        if is_admin:
            admin_ids.append(pin)
            print(f"[ADMIN] FOUND    -> ID: {pin:<8} | Name: {name:<18} | Role: {role}")
        else:
            print(f"  Normal User   -> ID: {pin:<8} | Name: {name:<18} | Role: {role}")
            
    print("-"*60)
    print(f"Total administrator IDs identified: {admin_ids}")
    return admin_ids

def parse_oplog(payload: str):
    """
    Parses OPLOG lines.
    Every operator PIN logging an event here belongs to an administrator.
    """
    print("\n" + "="*60)
    print("  PARSING TERMINAL OPERATION LOGS (OPLOG - ADMIN ACTIONS ONLY)")
    print("="*60)
    
    admin_ids = set()
    lines = payload.strip().split("\n")
    for line in lines:
        parts = line.strip().split("\t")
        if len(parts) < 3:
            continue
        
        operator_pin = parts[0]
        op_type_str = parts[1]
        timestamp = parts[2]
        
        try:
            op_type = int(op_type_str)
        except ValueError:
            op_type = -1
            
        # ZKTeco common operation types
        op_map = {
            0: "User Enrollment / Register",
            1: "Fingerprint Enrollment",
            2: "Password Enrollment",
            3: "Delete User",
            4: "Delete Fingerprint",
            5: "Modify Device Options",
        }
        op_desc = op_map.get(op_type, f"Other Operation ({op_type})")
        
        admin_ids.add(operator_pin)
        print(f"[ACTION] ADMIN  -> Operator ID: {operator_pin:<6} | Time: {timestamp} | Action: {op_desc}")
        
    print("-"*60)
    print(f"Unique administrator IDs logging actions: {list(admin_ids)}")
    return list(admin_ids)

if __name__ == "__main__":
    admin_pins_info = parse_userinfo(MOCK_USERINFO_PAYLOAD)
    admin_pins_op = parse_oplog(MOCK_OPLOG_PAYLOAD)
    
    all_admins = sorted(list(set(admin_pins_info + admin_pins_op)))
    print("\n" + "="*60)
    print(f"[SUMMARY] ALL IDENTIFIED ADMIN USER IDs ON DEVICE")
    print("="*60)
    print(f"Admin User IDs: {all_admins}")
    print("="*60 + "\n")

