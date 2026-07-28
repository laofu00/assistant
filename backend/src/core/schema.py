"""统一响应格式 — R[T] + PageResponse[T]"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class R(BaseModel, Generic[T]):
    """统一 API 响应

    code=0 表示成功，非 0 表示业务错误。
    对齐 Java 版 com.smart.home.common.web.R<T>。
    """

    code: int = 0
    data: T | None = None
    msg: str = "success"

    @classmethod
    def ok(cls, data: T | None = None, msg: str = "success") -> "R[T]":
        return cls(code=0, data=data, msg=msg)

    @classmethod
    def error(cls, code: int, msg: str, data: T | None = None) -> "R[T]":
        return cls(code=code, data=data, msg=msg)


class PageResponse(BaseModel, Generic[T]):
    """统一分页响应"""

    records: list[T]
    total: int
    page: int
    size: int

    @classmethod
    def of(cls, records: list[T], total: int, page: int, size: int) -> "PageResponse[T]":
        return cls(records=records, total=total, page=page, size=size)
