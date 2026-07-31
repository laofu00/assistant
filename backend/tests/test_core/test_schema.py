"""core/schema.py 统一响应格式测试"""

from src.core.schema import R, PageResponse


class TestR:
    def test_ok_default(self) -> None:
        r = R.ok()
        assert r.code == 0
        assert r.data is None
        assert r.msg == "success"

    def test_ok_with_data(self) -> None:
        r = R.ok(data={"key": "value"})
        assert r.code == 0
        assert r.data == {"key": "value"}

    def test_ok_with_custom_msg(self) -> None:
        r = R.ok(msg="操作成功")
        assert r.msg == "操作成功"

    def test_error(self) -> None:
        r = R.error(code=400, msg="Bad Request")
        assert r.code == 400
        assert r.msg == "Bad Request"
        assert r.data is None

    def test_error_with_data(self) -> None:
        r = R.error(code=500, msg="Internal Error", data={"detail": "..."})
        assert r.code == 500
        assert r.data == {"detail": "..."}

    def test_generic_type(self) -> None:
        """验证泛型约束"""
        r: R[str] = R.ok(data="hello")
        assert r.data == "hello"


class TestPageResponse:
    def test_of(self) -> None:
        records = [{"id": 1}, {"id": 2}]
        p = PageResponse.of(records, total=100, page=1, size=20)
        assert p.records == records
        assert p.total == 100
        assert p.page == 1
        assert p.size == 20

    def test_empty_records(self) -> None:
        p = PageResponse.of([], total=0, page=1, size=20)
        assert p.records == []
        assert p.total == 0
