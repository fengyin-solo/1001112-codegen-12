"""岸桥作业量统计口径：按设备编号与班次汇总作业流水，并实时关联岸桥台账（设备清单）。

取数原则：
- 明细每次都从 crane 台账现取设备状态，不做缓存，保证刷新后数字与设备清单一致；
- 作业量为空、设备编号在台账挂不上的记录逐条标出，但仍计入流水，不静默丢弃；
- 班次视图按班次汇总作业量，并给出参与设备在台账中的状态分布。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "cranestat"
CRANE_MODULE = "crane"

# 班次展示顺序，未在列表里的班次顺延到后面。
SHIFT_ORDER = ["早班", "中班", "夜班"]
# 设备状态口径与岸桥台账保持一致。
STATUS_ORDER = ["待指派", "作业中", "待保养", "已停机"]


class CraneStatService:
    def _ledger(self) -> dict[str, dict[str, Any]]:
        """按设备编号建立台账索引；每次调用都现取，保证与设备清单同步。"""
        return {
            str(row.get("设备编号", "")).strip(): row
            for row in store.rows(CRANE_MODULE)
            if str(row.get("设备编号", "")).strip()
        }

    def list_records(
        self,
        *,
        keyword: str | None = None,
        shift: str | None = None,
        abnormal: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._decorate(store.rows(MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if shift:
            rows = [row for row in rows if row.get("班次") == shift]
        if abnormal == "empty":
            rows = [row for row in rows if row.get("作业量为空")]
        elif abnormal == "unmatched":
            rows = [row for row in rows if row.get("设备编号挂不上")]
        elif abnormal:
            # 任意异常：作业量为空或挂不上台账
            rows = [row for row in rows if row.get("作业量为空") or row.get("设备编号挂不上")]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def shift_view(self) -> dict[str, Any]:
        """生成班次作业量视图：作业量汇总 + 台账设备状态分布。"""
        rows = self._decorate(store.rows(MODULE))
        shifts: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            shifts.setdefault(str(row.get("班次") or "未分班"), []).append(row)

        items: list[dict[str, Any]] = []
        for name in sorted(shifts, key=lambda value: (self._shift_rank(value), value)):
            group = shifts[name]
            # 作业量只累加有数值的记录，空值不按 0 蒙混过去
            amounts = [self._to_number(row.get("作业量")) for row in group]
            valid_amounts = [value for value in amounts if value is not None]
            total_amount = sum(valid_amounts)
            # 参与设备按设备编号去重；挂不上台账的编号不进状态分布
            device_codes = {
                str(row.get("设备编号", "")).strip()
                for row in group
                if str(row.get("设备编号", "")).strip()
            }
            ledger = self._ledger()
            status_distribution = {status: 0 for status in STATUS_ORDER}
            unmatched_devices: list[str] = []
            matched_devices = 0
            for code in sorted(device_codes):
                entry = ledger.get(code)
                if entry is None:
                    unmatched_devices.append(code)
                    continue
                matched_devices += 1
                status = str(entry.get("status") or "").strip() or "待指派"
                status_distribution[status] = status_distribution.get(status, 0) + 1
            items.append({
                "班次": name,
                "记录数": len(group),
                "作业量合计": total_amount,
                "参与设备数": len(device_codes),
                "已匹配设备数": matched_devices,
                "台均作业量": round(total_amount / matched_devices, 1) if matched_devices else 0,
                "作业量空值数": sum(1 for row in group if row.get("作业量为空")),
                "挂不上台账数": len(unmatched_devices),
                "设备状态分布": [
                    {"设备状态": status, "数量": status_distribution.get(status, 0)}
                    for status in STATUS_ORDER
                ],
                "挂不上设备编号": unmatched_devices,
            })

        # 台均作业量最低的班次标出来，方便定位哪个班次效率低
        if items:
            weakest = min(items, key=lambda item: float(item["台均作业量"]))
            weakest["效率偏低"] = True

        ledger = self._ledger()
        all_amounts = [
            value for value in (self._to_number(row.get("作业量")) for row in rows)
            if value is not None
        ]
        summary = {
            "台账设备数": len(ledger),
            "流水记录数": len(rows),
            "作业量合计": sum(all_amounts),
            "作业量空值数": sum(1 for row in rows if row.get("作业量为空")),
            "挂不上台账记录数": sum(1 for row in rows if row.get("设备编号挂不上")),
            "班次数": len(items),
        }
        return {"items": items, "summary": summary}

    def _decorate(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """给每条流水补台账设备状态与异常标记；保留原记录顺序与字段。"""
        ledger = self._ledger()
        decorated: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            code = str(row.get("设备编号", "")).strip()
            amount_empty = self._to_number(row.get("作业量")) is None
            ledger_entry = ledger.get(code) if code else None
            unmatched = bool(code) and ledger_entry is None
            item["作业量为空"] = amount_empty
            item["设备编号挂不上"] = unmatched
            item["台账设备状态"] = str(ledger_entry["status"]) if ledger_entry else None
            flags: list[str] = []
            if amount_empty:
                flags.append("作业量为空")
            if not code:
                flags.append("设备编号缺失")
            elif unmatched:
                flags.append("设备编号挂不上台账")
            item["异常标记"] = "、".join(flags)
            decorated.append(item)
        return decorated

    @staticmethod
    def _to_number(value: Any) -> float | None:
        """把作业量解析成数字；空值或非数字返回 None，交给调用方标出而不是当 0。"""
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _shift_rank(shift: str) -> int:
        return SHIFT_ORDER.index(shift) if shift in SHIFT_ORDER else len(SHIFT_ORDER)


service = CraneStatService()
