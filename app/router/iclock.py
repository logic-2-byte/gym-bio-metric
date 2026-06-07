import time
from datetime import datetime, date
from fastapi import APIRouter, Request, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db

router = APIRouter(tags=["iclock"])

# Global cache for device sync times to throttle database queries during polling
LAST_SYNC_TIMES: dict[str, float] = {}

# Device Super Admin PINs that must never be blocked on the biometric terminal
DEVICE_SUPERADMIN_PINS = {0, 6, 7, 8, 17, 79, 111, 784, 855, 5050, 9999}


# Helper to parse ZKTeco attendance logs
def parse_attlog_line(line: str):
    parts = line.strip().split()
    if len(parts) < 3:
        return None
    pin = parts[0]
    dt_str = f"{parts[1]} {parts[2]}"
    try:
        timestamp = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return pin, timestamp
    except Exception:
        return None

# Helper to update device last seen timestamp
async def update_device_last_seen(sn: str, db: AsyncSession):
    if sn:
        try:
            query = text("UPDATE public.tenants SET biometric_device_last_seen = NOW() WHERE biometric_device_sn = :sn")
            await db.execute(query, {"sn": sn})
            await db.commit()
            print(f"Updated last seen for device: {sn}")
        except Exception as e:
            print(f"Error updating device last seen: {e}")

@router.get("/api/device/status")
async def get_device_status(sn: str, db: AsyncSession = Depends(get_db)):
    query = text("SELECT tenant_id, gym_name, biometric_device_last_seen FROM public.tenants WHERE biometric_device_sn = :sn LIMIT 1")
    result = await db.execute(query, {"sn": sn})
    row = result.fetchone()
    if not row:
        return {"status": "not_registered", "last_seen": None}
    
    tenant_id, gym_name, last_seen = row
    if not last_seen:
        return {"status": "offline", "last_seen": None, "gym_name": gym_name}
    
    now = datetime.now()
    # Handle timezone differences if any, or just direct subtraction
    diff = (now - last_seen).total_seconds()
    
    # ZKTeco ADMS device standard poll interval is ~15-60 seconds. We allow 120s buffer.
    is_online = diff < 120
    return {
        "status": "online" if is_online else "offline",
        "last_seen": last_seen.isoformat(),
        "gym_name": gym_name,
        "seconds_since_last_seen": diff
    }

@router.post("/api/device/command")
async def queue_device_command(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON payload"}
        
    sn = payload.get("device_sn")
    member_id = payload.get("member_id")
    action = payload.get("action") # "enable" or "block"
    
    if not member_id or not action:
        return {"ok": False, "error": "Missing parameters (member_id and action are required)"}
        
    if not sn:
        # Resolve device SN by scanning all active tenants for this member_id
        tenant_list_query = text("SELECT tenant_id, biometric_device_sn FROM public.tenants WHERE biometric_device_sn IS NOT NULL")
        try:
            tenant_result = await db.execute(tenant_list_query)
            tenants = tenant_result.fetchall()
        except Exception as e:
            print(f"Error fetching tenants: {e}")
            return {"ok": False, "error": "Database error fetching tenants"}
            
        for tenant_id, device_sn in tenants:
            member_exists_query = text(f"SELECT EXISTS(SELECT 1 FROM {tenant_id}.members WHERE client_id = :member_id)")
            try:
                exists_result = await db.execute(member_exists_query, {"member_id": member_id})
                exists_row = exists_result.fetchone()
                if exists_row and exists_row[0]:
                    sn = device_sn
                    break
            except Exception:
                continue
                
        if not sn:
            return {"ok": False, "error": f"Member {member_id} not found in any tenant schema with a linked biometric device"}
        
    target_grp = 1 if action == "enable" else 3
    cmd_text = f"DATA UPDATE USERINFO PIN={member_id}\tGrp={target_grp}"
    
    insert_cmd = text(
        "INSERT INTO public.biometric_commands (device_sn, command_text) "
        "VALUES (:sn, :cmd_text)"
    )
    try:
        await db.execute(insert_cmd, {
            "sn": sn,
            "cmd_text": cmd_text
        })
        await db.commit()
        print(f"Manually queued command for member {member_id} on device {sn}: Grp={target_grp}")
        return {"ok": True, "message": f"Queued {action} command for member {member_id}"}
    except Exception as e:
        print(f"Error queueing manual command: {e}")
        return {"ok": False, "error": str(e)}

async def sync_member_status_commands(sn: str, db: AsyncSession):
    # 1. Resolve tenant schema
    tenant_query = text("SELECT tenant_id FROM public.tenants WHERE biometric_device_sn = :sn LIMIT 1")
    tenant_result = await db.execute(tenant_query, {"sn": sn})
    tenant_row = tenant_result.fetchone()
    if not tenant_row:
        return
    tenant_id = tenant_row[0]
    
    # 2. Get all members and their latest subscription
    query = text(f"""
        SELECT m.client_id,
               m.status as member_status,
               m.biometric_override,
               EXISTS (
                   SELECT 1 FROM {tenant_id}.member_subscriptions s
                   WHERE s.member_id = m.client_id
                     AND s.status NOT IN ('DEACTIVE', 'EXPIRED')
                     AND s.start_date <= NOW()
                     AND s.end_date >= NOW()
               ) as has_active_sub
        FROM {tenant_id}.members m
    """)
    try:
        result = await db.execute(query)
        rows = result.fetchall()
    except Exception as e:
        print(f"Error fetching members during sync: {e}")
        return
        
    member_active_map = {}
    for r in rows:
        client_id, m_status, bio_override, has_active_sub = r
        is_active = False
        if bio_override == 'ENABLE':
            is_active = True
        elif m_status == 'ACTIVE' and has_active_sub:
            is_active = True
        member_active_map[client_id] = is_active
        
    # 3. Get recent commands to build the last known group map for each member
    cmd_query = text("""
        SELECT command_text FROM public.biometric_commands
        WHERE device_sn = :sn AND command_text LIKE 'DATA UPDATE USERINFO PIN=%'
        ORDER BY id DESC
    """)
    try:
        cmd_result = await db.execute(cmd_query, {"sn": sn})
        cmd_rows = cmd_result.fetchall()
    except Exception as e:
        print(f"Error fetching commands during sync: {e}")
        return
        
    member_last_grp = {}
    for r in cmd_rows:
        cmd_text = r[0]
        try:
            if "PIN=" in cmd_text and "Grp=" in cmd_text:
                parts = cmd_text.split("PIN=")
                sub_parts = parts[1].split("\tGrp=")
                if len(sub_parts) < 2:
                    sub_parts = parts[1].split(" Grp=")
                pin = int(sub_parts[0].strip())
                grp = int(sub_parts[1].split()[0].strip())
                if pin not in member_last_grp:
                    member_last_grp[pin] = grp
        except Exception:
            continue
            
    # 4. Compare and queue commands for any status mismatch
    for member_id, is_active in member_active_map.items():
        if member_id in DEVICE_SUPERADMIN_PINS:
            continue
            
        target_group = 1 if is_active else 3
        last_grp = member_last_grp.get(member_id)
        
        should_queue = False
        if last_grp is not None:
            if last_grp != target_group:
                should_queue = True
        else:
            if target_group == 3:
                # Expired member needs to be blocked
                should_queue = True
                
        if should_queue:
            cmd_text = f"DATA UPDATE USERINFO PIN={member_id}\tGrp={target_group}"
            insert_cmd = text(
                "INSERT INTO public.biometric_commands (device_sn, command_text) "
                "VALUES (:sn, :cmd_text)"
            )
            try:
                await db.execute(insert_cmd, {
                    "sn": sn,
                    "cmd_text": cmd_text
                })
                print(f"Proactive sync queued command for member {member_id}: Grp={target_group}")
            except Exception as e:
                print(f"Error inserting command during sync: {e}")
                
    try:
        await db.commit()
    except Exception as e:
        print(f"Error committing sync changes: {e}")


@router.api_route("/iclock/getrequest", methods=["GET", "POST"])
async def getrequest(request: Request, db: AsyncSession = Depends(get_db)) -> PlainTextResponse:
    if request.method == "GET":
        sn = request.query_params.get("SN")
        if not sn:
            return PlainTextResponse("OK", media_type="text/plain")
        
        # Update last seen timestamp
        await update_device_last_seen(sn, db)
        
        # Check for unprocessed biometric commands for this device SN
        query = text(
            "SELECT id, command_text FROM public.biometric_commands "
            "WHERE device_sn = :sn AND processed = FALSE "
            "ORDER BY id ASC LIMIT 1"
        )
        result = await db.execute(query, {"sn": sn})
        row = result.fetchone()
        
        if not row:
            # Throttle the sync check to run at most once every 60 seconds (1 minute) to reduce database load during polling
            current_time = time.time()
            last_sync = LAST_SYNC_TIMES.get(sn, 0.0)
            if current_time - last_sync > 60:
                # Proactively check and sync member status commands
                await sync_member_status_commands(sn, db)
                LAST_SYNC_TIMES[sn] = current_time
                
                # Fetch again in case any commands were queued
                result = await db.execute(query, {"sn": sn})
                row = result.fetchone()
            
        if row:
            cmd_id, cmd_text = row
            resp_text = f"C:{cmd_id}:{cmd_text.strip()}"
            print(f"Sending command to device {sn}: {resp_text}")
            return PlainTextResponse(resp_text, media_type="text/plain")
            
        return PlainTextResponse("OK", media_type="text/plain")
        
    body = await request.body()
    print("GETREQUEST POST:", body.decode(errors="ignore"))
    return PlainTextResponse("OK", media_type="text/plain")


@router.api_route("/iclock/cdata", methods=["GET", "POST"])
async def cdata(request: Request, db: AsyncSession = Depends(get_db)) -> PlainTextResponse:
    print("CDATA RECEIVED")
    sn = request.query_params.get("SN")
    table = request.query_params.get("table")
    body = await request.body()
    body_str = body.decode(errors="ignore")
    print("BODY:", body_str)

    if sn:
        await update_device_last_seen(sn, db)

    if request.method == "POST" and sn and table == "ATTLOG":
        # Resolve tenant schema
        tenant_query = text("SELECT tenant_id FROM public.tenants WHERE biometric_device_sn = :sn LIMIT 1")
        tenant_result = await db.execute(tenant_query, {"sn": sn})
        tenant_row = tenant_result.fetchone()
        if tenant_row:
            tenant_id = tenant_row[0]
            print(f"Resolved tenant schema: {tenant_id}")
            
            lines = body_str.strip().split("\n")
            for line in lines:
                parsed = parse_attlog_line(line)
                if parsed:
                    pin, timestamp = parsed
                    try:
                        member_id = int(pin)
                    except ValueError:
                        continue
                    
                    if member_id in DEVICE_SUPERADMIN_PINS:
                        print(f"Skipping command updates for Super Admin user ID: {member_id}")
                        try:
                            # 1. Log attendance directly using Postgres ON CONFLICT UPSERT in the tenant schema
                            att_query = text(f"""
                                INSERT INTO {tenant_id}.attendance (member_id, attendance_date, check_in, check_out, device_name, status)
                                VALUES (:member_id, :attendance_date, :timestamp, :timestamp, 'Main Entrance Biometric', 'Present')
                                ON CONFLICT (member_id, attendance_date) DO UPDATE
                                SET check_out = CASE WHEN :timestamp > {tenant_id}.attendance.check_out THEN :timestamp ELSE {tenant_id}.attendance.check_out END,
                                    check_in = CASE WHEN :timestamp < {tenant_id}.attendance.check_in THEN :timestamp ELSE {tenant_id}.attendance.check_in END,
                                    updated_at = NOW();
                            """)
                            await db.execute(att_query, {
                                "member_id": member_id,
                                "attendance_date": timestamp.date(),
                                "timestamp": timestamp
                            })
                            await db.commit()
                            print(f"Logged attendance for Super Admin member {member_id} at {timestamp} in schema {tenant_id}")
                        except Exception as err:
                            await db.rollback()
                            print(f"Skipping log for Super Admin member {member_id}: database integrity error or unregistered user: {err}")
                        continue

                    try:
                        # 1. Log attendance directly using Postgres ON CONFLICT UPSERT in the tenant schema
                        att_query = text(f"""
                            INSERT INTO {tenant_id}.attendance (member_id, attendance_date, check_in, check_out, device_name, status)
                            VALUES (:member_id, :attendance_date, :timestamp, :timestamp, 'Main Entrance Biometric', 'Present')
                            ON CONFLICT (member_id, attendance_date) DO UPDATE
                            SET check_out = CASE WHEN :timestamp > {tenant_id}.attendance.check_out THEN :timestamp ELSE {tenant_id}.attendance.check_out END,
                                check_in = CASE WHEN :timestamp < {tenant_id}.attendance.check_in THEN :timestamp ELSE {tenant_id}.attendance.check_in END,
                                updated_at = NOW();
                        """)
                        await db.execute(att_query, {
                            "member_id": member_id,
                            "attendance_date": timestamp.date(),
                            "timestamp": timestamp
                        })
                        await db.commit()
                        print(f"Logged attendance for member {member_id} at {timestamp} in schema {tenant_id}")
                    except Exception as err:
                        await db.rollback()
                        print(f"Skipping log for member {member_id}: database integrity error or unregistered user: {err}")
                        continue



                    try:
                        # 2. Check if member is active or expired
                        member_query = text(f"""
                            SELECT m.status as member_status, 
                                   m.biometric_override,
                                   EXISTS (
                                       SELECT 1 FROM {tenant_id}.member_subscriptions s
                                       WHERE s.member_id = m.client_id
                                         AND s.status NOT IN ('DEACTIVE', 'EXPIRED')
                                         AND s.start_date <= NOW()
                                         AND s.end_date >= NOW()
                                   ) as has_active_sub
                            FROM {tenant_id}.members m
                            WHERE m.client_id = :member_id;
                        """)
                        member_result = await db.execute(member_query, {"member_id": member_id})
                        member_row = member_result.fetchone()
                        
                        if not member_row:
                            print(f"Member {member_id} not found in database. Skipping device command updates.")
                            continue
                        
                        m_status, bio_override, has_active_sub = member_row
                        is_active = False
                        if bio_override == 'ENABLE':
                            is_active = True
                        elif m_status == 'ACTIVE' and has_active_sub:
                            is_active = True
                        
                        target_group = 1 if is_active else 3
                        print(f"Member {member_id} active status: {is_active}. Target group: {target_group}")

                        
                        # 3. Check last queued group command to avoid duplicate commands
                        last_cmd_query = text(
                            "SELECT command_text FROM public.biometric_commands "
                            "WHERE device_sn = :sn AND command_text LIKE :pattern "
                            "ORDER BY id DESC LIMIT 1"
                        )
                        last_cmd_result = await db.execute(last_cmd_query, {
                            "sn": sn,
                            "pattern": f"%PIN={member_id}%"
                        })
                        last_cmd_row = last_cmd_result.fetchone()
                        
                        should_queue = True
                        if last_cmd_row:
                            last_cmd_text = last_cmd_row[0]
                            if f"Grp={target_group}" in last_cmd_text:
                                should_queue = False
                                print(f"Group command Grp={target_group} already queued/sent previously. Skipping.")
                                
                        if should_queue:
                            cmd_text = f"DATA UPDATE USERINFO PIN={member_id}\tGrp={target_group}"
                            insert_cmd = text(
                                "INSERT INTO public.biometric_commands (device_sn, command_text) "
                                "VALUES (:sn, :cmd_text)"
                            )
                            await db.execute(insert_cmd, {
                                "sn": sn,
                                "cmd_text": cmd_text
                            })
                            await db.commit()
                            print(f"Queued command for member {member_id}: Grp={target_group}")
                    except Exception as inner_err:
                        print(f"Error checking status/queueing command for member {member_id}: {inner_err}")
        else:
            print(f"Warning: Serial number {sn} is not mapped to any tenant!")

    return PlainTextResponse("OK", media_type="text/plain")


@router.api_route("/iclock/registry", methods=["GET", "POST"])
async def registry(request: Request) -> PlainTextResponse:
    body = await request.body()
    print("REGISTRY:", body.decode(errors="ignore"))
    return PlainTextResponse("OK", media_type="text/plain")


@router.api_route("/iclock/devicecmd", methods=["GET", "POST"])
async def devicecmd(request: Request, db: AsyncSession = Depends(get_db)) -> PlainTextResponse:
    print("DEVICECMD RECEIVED")
    sn = request.query_params.get("SN")
    body = await request.body()
    body_str = body.decode(errors="ignore")
    print("BODY:", body_str)

    if sn:
        await update_device_last_seen(sn, db)

    if request.method == "POST" and body_str:
        params = {}
        for pair in body_str.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
                
        cmd_id_str = params.get("ID")
        ret_str = params.get("Return")
        
        if cmd_id_str and ret_str:
            try:
                cmd_id = int(cmd_id_str)
                ret_code = int(ret_str)
                if ret_code == 0:
                    update_query = text(
                        "UPDATE public.biometric_commands "
                        "SET processed = TRUE "
                        "WHERE id = :cmd_id"
                    )
                    await db.execute(update_query, {"cmd_id": cmd_id})
                    await db.commit()
                    print(f"Command {cmd_id} processed successfully by device {sn}.")
                else:
                    print(f"Command {cmd_id} execution failed on device {sn} with return code {ret_code}.")
            except ValueError:
                pass

    return PlainTextResponse("OK", media_type="text/plain")
