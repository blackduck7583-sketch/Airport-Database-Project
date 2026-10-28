from datetime import datetime, timedelta

from .db import connect


FLIGHT_STATUSES = {"SCHEDULED", "DELAYED", "BOARDING", "DEPARTED", "ARRIVED", "CANCELLED"}


class ValidationError(ValueError):
    pass


class ConflictError(ValueError):
    pass


def parse_time(value, field_name):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} 必须是 ISO 8601 日期时间")
    return parsed


class AirportService:
    def __init__(self, database):
        self.database = database

    def dashboard(self):
        with connect(self.database) as db:
            flights = db.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status = 'DELAYED' THEN 1 ELSE 0 END) AS delayed,
                       SUM(CASE WHEN status IN ('BOARDING', 'SCHEDULED') THEN 1 ELSE 0 END) AS active
                FROM flights WHERE date(scheduled_time) = date('now', 'localtime')
            """).fetchone()
            gates = db.execute("SELECT COUNT(*) AS total FROM gates WHERE active = 1").fetchone()
            occupied = db.execute("""
                SELECT COUNT(DISTINCT ga.gate_id) AS total FROM gate_assignments ga
                JOIN flights f ON f.id = ga.flight_id
                WHERE datetime(ga.occupied_from) <= datetime('now', 'localtime')
                  AND datetime(ga.occupied_until) > datetime('now', 'localtime')
                  AND f.status != 'CANCELLED'
            """).fetchone()
            return {
                "flights_today": flights["total"] or 0,
                "delayed_today": flights["delayed"] or 0,
                "active_today": flights["active"] or 0,
                "gates_total": gates["total"] or 0,
                "gates_occupied": occupied["total"] or 0,
            }

    def options(self):
        with connect(self.database) as db:
            airlines = [dict(row) for row in db.execute("SELECT id, code, name FROM airlines ORDER BY code")]
            aircraft = [dict(row) for row in db.execute("SELECT id, code, name FROM aircraft_types ORDER BY code")]
            return {"airlines": airlines, "aircraft_types": aircraft, "statuses": sorted(FLIGHT_STATUSES)}

    def gates(self):
        with connect(self.database) as db:
            return [dict(row) for row in db.execute("""
                SELECT g.id, g.code, g.terminal, g.gate_type, g.active,
                       COUNT(DISTINCT CASE WHEN datetime(ga.occupied_from) <= datetime('now', 'localtime')
                         AND datetime(ga.occupied_until) > datetime('now', 'localtime')
                         AND f.status != 'CANCELLED' THEN ga.flight_id END) AS occupied
                FROM gates g LEFT JOIN gate_assignments ga ON ga.gate_id = g.id
                LEFT JOIN flights f ON f.id = ga.flight_id
                GROUP BY g.id ORDER BY g.terminal, g.code
            """)]

    def list_flights(self, filters):
        clauses, params = [], []
        query = (filters.get("q") or "").strip()
        if query:
            clauses.append("(f.flight_no LIKE ? OR a.name LIKE ? OR a.code LIKE ? OR f.origin_destination LIKE ? OR g.code LIKE ?)")
            params.extend([f"%{query}%"] * 5)
        for key, column in (("status", "f.status"), ("direction", "f.direction")):
            value = (filters.get(key) or "").strip().upper()
            if value:
                allowed = FLIGHT_STATUSES if key == "status" else {"ARRIVAL", "DEPARTURE"}
                if value not in allowed:
                    raise ValidationError(f"无效的{key}筛选条件")
                clauses.append(f"{column} = ?")
                params.append(value)
        day = (filters.get("date") or "").strip()
        if day:
            try:
                datetime.strptime(day, "%Y-%m-%d")
            except ValueError:
                raise ValidationError("日期筛选格式应为 YYYY-MM-DD")
            clauses.append("date(f.scheduled_time) = ?")
            params.append(day)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with connect(self.database) as db:
            rows = db.execute(f"""
                SELECT f.id, f.flight_no, a.code AS airline_code, a.name AS airline_name,
                       ac.code AS aircraft_code, f.direction, f.origin_destination,
                       f.scheduled_time, f.status, g.code AS gate_code,
                       COALESCE(d.delay_minutes, 0) AS delay_minutes,
                       COALESCE(d.delay_reason, '') AS delay_reason
                FROM flights f
                JOIN airlines a ON a.id = f.airline_id
                JOIN aircraft_types ac ON ac.id = f.aircraft_type_id
                LEFT JOIN gate_assignments ga ON ga.flight_id = f.id
                LEFT JOIN gates g ON g.id = ga.gate_id
                LEFT JOIN (
                    SELECT flight_id, SUM(delay_minutes) AS delay_minutes,
                           GROUP_CONCAT(reason, '；') AS delay_reason
                    FROM delay_records GROUP BY flight_id
                ) d ON d.flight_id = f.id
                {where}
                ORDER BY f.scheduled_time LIMIT 500
            """, params).fetchall()
            return [dict(row) for row in rows]

    def create_flight(self, data):
        required = ("flight_no", "airline_id", "aircraft_type_id", "direction", "origin_destination", "scheduled_time")
        missing = [key for key in required if not str(data.get(key, "")).strip()]
        if missing:
            raise ValidationError("请填写必填字段：" + ", ".join(missing))
        direction = str(data["direction"]).upper()
        if direction not in {"ARRIVAL", "DEPARTURE"}:
            raise ValidationError("航班方向必须为到达或出发")
        scheduled = parse_time(data["scheduled_time"], "计划时间")
        flight_no = str(data["flight_no"]).strip().upper()
        if len(flight_no) > 12:
            raise ValidationError("航班号长度不能超过 12 个字符")
        with connect(self.database) as db:
            try:
                cursor = db.execute("""
                    INSERT INTO flights(flight_no, airline_id, aircraft_type_id, direction,
                                        origin_destination, scheduled_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (flight_no, int(data["airline_id"]), int(data["aircraft_type_id"]), direction,
                      str(data["origin_destination"]).strip(), scheduled.isoformat(timespec="minutes")))
            except (ValueError, TypeError):
                raise ValidationError("航空公司或机型无效")
            except Exception as error:
                if "UNIQUE constraint failed" in str(error):
                    raise ConflictError("该航班号、方向和计划时间已存在")
                if "FOREIGN KEY constraint failed" in str(error):
                    raise ValidationError("航空公司或机型不存在")
                raise
            return {"id": cursor.lastrowid, "flight_no": flight_no, "status": "SCHEDULED"}

    def update_status(self, flight_id, status):
        status = str(status).upper().strip()
        if status not in FLIGHT_STATUSES:
            raise ValidationError("无效的航班状态")
        with connect(self.database) as db:
            cursor = db.execute("UPDATE flights SET status = ? WHERE id = ?", (status, flight_id))
            if cursor.rowcount == 0:
                raise ValidationError("航班不存在")
            return {"id": flight_id, "status": status}

    def assign_gate(self, flight_id, gate_id):
        try:
            gate_id = int(gate_id)
        except (ValueError, TypeError):
            raise ValidationError("请选择有效登机口")
        with connect(self.database) as db:
            db.execute("BEGIN IMMEDIATE")
            flight = db.execute("""
                SELECT f.id, f.scheduled_time, f.direction, f.status,
                       ac.turnaround_minutes
                FROM flights f JOIN aircraft_types ac ON ac.id = f.aircraft_type_id
                WHERE f.id = ?
            """, (flight_id,)).fetchone()
            gate = db.execute("SELECT id, code FROM gates WHERE id = ? AND active = 1", (gate_id,)).fetchone()
            if not flight:
                raise ValidationError("航班不存在")
            if not gate:
                raise ValidationError("登机口不存在或已停用")
            if flight["status"] == "CANCELLED":
                raise ConflictError("已取消航班不能分配登机口")
            scheduled = parse_time(flight["scheduled_time"], "计划时间")
            start = scheduled - timedelta(minutes=30) if flight["direction"] == "DEPARTURE" else scheduled
            end = scheduled + timedelta(minutes=flight["turnaround_minutes"])
            overlap = db.execute("""
                SELECT f.flight_no FROM gate_assignments ga JOIN flights f ON f.id = ga.flight_id
                WHERE ga.gate_id = ? AND ga.flight_id != ?
                  AND f.status != 'CANCELLED'
                  AND datetime(ga.occupied_from) < datetime(?)
                  AND datetime(ga.occupied_until) > datetime(?)
                LIMIT 1
            """, (gate_id, flight_id, end.isoformat(timespec="minutes"), start.isoformat(timespec="minutes"))).fetchone()
            if overlap:
                raise ConflictError(f"登机口 {gate['code']} 时段冲突：与航班 {overlap['flight_no']} 占用时间重叠")
            db.execute("""
                INSERT INTO gate_assignments(flight_id, gate_id, occupied_from, occupied_until)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(flight_id) DO UPDATE SET gate_id = excluded.gate_id,
                  occupied_from = excluded.occupied_from, occupied_until = excluded.occupied_until,
                  assigned_at = CURRENT_TIMESTAMP
            """, (flight_id, gate_id, start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes")))
            return {"flight_id": flight_id, "gate_id": gate_id, "gate_code": gate["code"],
                    "occupied_from": start.isoformat(timespec="minutes"),
                    "occupied_until": end.isoformat(timespec="minutes")}

    def record_delay(self, flight_id, data):
        try:
            minutes = int(data.get("delay_minutes", 0))
        except (ValueError, TypeError):
            raise ValidationError("延误分钟数必须为正整数")
        reason = str(data.get("reason", "")).strip()
        if minutes <= 0 or not reason:
            raise ValidationError("请填写大于 0 的延误分钟数和延误原因")
        with connect(self.database) as db:
            db.execute("BEGIN IMMEDIATE")
            flight = db.execute("SELECT status FROM flights WHERE id = ?", (flight_id,)).fetchone()
            if not flight:
                raise ValidationError("航班不存在")
            if flight["status"] in {"CANCELLED", "DEPARTED", "ARRIVED"}:
                raise ConflictError("已取消或已完成的航班不能新增延误记录")
            cursor = db.execute("INSERT INTO delay_records(flight_id, delay_minutes, reason) VALUES (?, ?, ?)",
                                (flight_id, minutes, reason[:200]))
            db.execute("UPDATE flights SET status = 'DELAYED' WHERE id = ?", (flight_id,))
            return {"id": cursor.lastrowid, "flight_id": flight_id, "delay_minutes": minutes, "reason": reason[:200]}

