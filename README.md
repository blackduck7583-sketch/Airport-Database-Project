# 机场运营数据管理系统

一个可本地运行的机场航班与登机口管理演示系统，围绕航班计划、登机口分配和延误记录构建。界面为中文，后端提供 JSON API，数据存储在 SQLite。

## 功能

- 航班信息录入、航班号/航空公司/航线/登机口多条件查询和状态更新。
- 登机口分配冲突校验：根据计划时间、航班方向和机型周转时长计算占用区间，防止同一登机口的时间重叠。
- 延误事件登记，记录延误分钟数、原因和时间，并自动把航班状态更新为“延误”。
- 运行总览指标和登机口当前占用视图。
- 参数化 SQL、外键约束、唯一约束和常用查询索引。
- `tools/load_test.py` 提供可配置并发量的 HTTP 负载测试脚本。

## 技术结构

```text
浏览器界面（HTML / CSS / JavaScript）
            ↓ JSON API
Flask 路由与业务服务（airport_ops/__init__.py、services.py）
            ↓ 参数化 SQL
SQLite 数据访问与表结构（airport_ops/db.py）
```

核心表：`airlines`、`aircraft_types`、`gates`、`flights`、`gate_assignments`、`delay_records`。航班列表通过多表 JOIN 汇总航空公司、机型、登机口和延误记录。

## 本地运行

需要 Python 3.10 或更新版本。

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

打开 `http://127.0.0.1:5000`。首次启动会创建 `instance/airport_operations.sqlite3`，并写入航空公司、机型和登机口基础数据。可通过环境变量 `AIRPORT_DATABASE` 指定其他 SQLite 文件路径。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/dashboard` | 今日航班与登机口指标 |
| GET | `/api/flights?q=&status=&direction=&date=` | 航班多条件查询（最多 500 条） |
| POST | `/api/flights` | 创建航班 |
| PATCH | `/api/flights/{id}/status` | 更新航班状态 |
| POST | `/api/flights/{id}/assignments` | 分配或更换登机口 |
| POST | `/api/flights/{id}/delays` | 新增延误记录 |
| GET | `/api/gates` | 查看登机口和当前占用状态 |
| GET | `/api/options` | 获取航空公司、机型和状态选项 |

创建航班请求示例：

```json
{
  "flight_no": "CA1234",
  "airline_id": 1,
  "aircraft_type_id": 1,
  "direction": "DEPARTURE",
  "origin_destination": "上海虹桥",
  "scheduled_time": "2026-10-29T09:30"
}
```

## 负载测试

先在一个终端启动服务，再在另一个终端运行：

```bash
python tools/load_test.py --url http://127.0.0.1:5000 --requests 500 --workers 25
```

脚本报告成功数、失败数、吞吐量和响应时间分位数。结果取决于本机硬件、SQLite 文件位置和并发设置。

## 业务规则与范围

- 登机口占用：出发航班从计划时间前 30 分钟开始占用；到达航班从计划到达时间开始占用。占用结束时间按机型配置的周转分钟计算。
- 已取消航班不能分配登机口；已取消、已起飞或已到达航班不能新增延误记录。
- SQLite 适合单机演示或小规模使用。多进程、多实例部署时应迁移到 PostgreSQL 等服务端数据库，并使用持久化存储、认证和访问控制。
- 基础航空公司、机型和登机口可在 `airport_ops/db.py` 的 `SEED` SQL 中调整。

