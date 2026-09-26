"""岸桥作业业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.seed import CRANE_WORKLOAD_ROWS
from app.store import store

MODULE = "crane"
REQUIRED_FIELDS = ["设备编号", "岸桥型号", "额定起重量"]
STATUS_ORDER = ["待指派", "作业中", "待保养", "已停机"]
ACTION_RULES = {"指派作业": "作业中", "安排保养": "待保养", "停机检修": "已停机"}
NEGATIVE_ACTIONS = []

# 作业量统计用的班次顺序；不在序列里的班次排在后面，保证视图稳定。
SHIFT_ORDER = ["早班", "中班", "晚班"]
ISSUE_NO_AMOUNT = "作业量为空"
ISSUE_NO_DEVICE = "设备编号未挂到台账"


def _parse_amount(value: Any) -> float | None:
    """把上报的作业量转成数字；空值或写坏了的值都按“空”处理，交给问题清单标出。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_amount(value: float) -> int | float:
    """作业量按自然数上报，能整除就按整数展示，避免视图里出现 86.0。"""
    return int(value) if value == int(value) else value


class CraneService:
    def __init__(self) -> None:
        # 上报记录独立于台账存放，进程内可追加，刷新统计时实时与台账核对。
        self._workload_rows: list[dict[str, Any]] = [dict(row) for row in CRANE_WORKLOAD_ROWS]

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"岸桥 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于岸桥作业可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"岸桥已{action}"

    def workload_view(
        self,
        *,
        keyword: str | None = None,
        shift: str | None = None,
    ) -> dict[str, Any]:
        """岸桥作业量统计：上报记录逐条与设备台账核对，再按班次汇总。

        返回四块内容：明细记录（含核对结果）、班次作业量视图（含设备状态分布）、
        待核实记录（作业量为空或设备编号挂不上台账）、以及与设备清单对齐用的汇总数字。
        """
        ledger = store.rows(MODULE)
        ledger_by_code = {str(row.get("设备编号") or "").strip(): row for row in ledger}

        records: list[dict[str, Any]] = []
        for row in self._workload_rows:
            code = str(row.get("设备编号") or "").strip()
            device = ledger_by_code.get(code)
            amount = _parse_amount(row.get("作业量"))
            issues: list[str] = []
            if amount is None:
                issues.append(ISSUE_NO_AMOUNT)
            if device is None:
                issues.append(ISSUE_NO_DEVICE)
            records.append({
                "id": row.get("id"),
                "设备编号": code or "（未填）",
                "班次": str(row.get("班次") or "").strip() or "未排班",
                "司机姓名": str(row.get("司机姓名") or "").strip() or "—",
                "作业区域": str(row.get("作业区域") or "").strip() or "—",
                "作业量": _format_amount(amount) if amount is not None else None,
                "设备状态": str(device.get("status")) if device else "台账外设备",
                "issues": issues,
            })

        if keyword:
            records = [row for row in records if keyword in str(row["设备编号"])]
        if shift:
            records = [row for row in records if row["班次"] == shift]

        shift_names = [name for name in SHIFT_ORDER if any(row["班次"] == name for row in records)]
        shift_names += sorted({str(row["班次"]) for row in records} - set(shift_names))
        shift_view = [self._shift_row(name, records) for name in shift_names]

        flagged = [row for row in records if row["issues"]]
        total_amount = sum(float(row["作业量"]) for row in records if row["作业量"] is not None)
        summary = {
            "台账设备数": len(ledger),
            "作业记录数": len(records),
            "作业量总计": _format_amount(total_amount),
            "待核实记录": len(flagged),
        }
        return {
            "summary": summary,
            "shift_view": shift_view,
            "records": records,
            "flagged": flagged,
            "shifts": shift_names,
        }

    @staticmethod
    def _shift_row(name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        """汇总单个班次：作业量合计、记录条数，以及该班次用到的设备状态分布。"""
        rows = [row for row in records if row["班次"] == name]
        status_dist: dict[str, int] = {}
        for row in rows:
            status = str(row["设备状态"])
            status_dist[status] = status_dist.get(status, 0) + 1
        amount = sum(float(row["作业量"]) for row in rows if row["作业量"] is not None)
        return {
            "班次": name,
            "作业量合计": _format_amount(amount),
            "记录条数": len(rows),
            "待核实条数": sum(1 for row in rows if row["issues"]),
            "设备状态分布": status_dist,
        }
