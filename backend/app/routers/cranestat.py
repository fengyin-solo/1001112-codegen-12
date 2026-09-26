"""岸桥作业量统计接口：按设备编号与班次查看作业明细，并提供班次作业量视图。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import PageResult
from app.services.cranestat import service

router = APIRouter(prefix="/api/crane-stat", tags=["岸桥作业量统计"])

LIST_FIELDS = ["设备编号", "班次", "作业量", "司机姓名", "作业区域", "台账设备状态", "异常标记"]
SHIFTS = ["早班", "中班", "夜班"]


@router.get("/records", response_model=PageResult[dict])
def list_records(
    keyword: str | None = Query(default=None, description="按设备编号检索"),
    shift: str | None = Query(default=None, description="早班、中班、夜班"),
    abnormal: str | None = Query(default=None, description="all=全部异常、empty=作业量为空、unmatched=设备编号挂不上台账"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设备编号与班次列出岸桥作业量、司机与作业区域，并带台账状态与异常标记。"""
    if size > 500:
        raise HTTPException(status_code=400, detail="每页最多 500 条，请缩小分页范围")
    if abnormal and abnormal not in {"all", "empty", "unmatched"}:
        raise HTTPException(status_code=400, detail="abnormal 只支持 all、empty、unmatched")
    items, total = service.list_records(
        keyword=keyword, shift=shift, abnormal=abnormal, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/shifts")
def shift_view() -> dict[str, object]:
    """班次作业量视图：各班次作业量汇总与台账设备状态分布，数据实时取自设备清单。"""
    return service.shift_view()
