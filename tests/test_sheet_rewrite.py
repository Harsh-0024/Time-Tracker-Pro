"""_rewrite_sheet_rows: the tail-safe path (rows appended to the sheet after the
snapshot) must be able to delete surplus baseline rows."""
from time_tracker_pro.services.sync import _rewrite_sheet_rows


class FakeSheety:
    def __init__(self, rows):
        self.rows = {int(r["id"]): dict(r) for r in rows}
        self.order = [int(r["id"]) for r in rows]
        self.calls = []

    def make_request_bypass_outbox(self, method, path, body):
        self.calls.append((method, path))
        if method == "GET":
            return True, {"logs": [self.rows[i] for i in self.order]}, None
        if method == "PUT":
            self.rows[int(path)] = {"id": int(path), **body["logs"]}
            return True, {"logs": self.rows[int(path)]}, None
        if method == "DELETE":
            self.rows.pop(int(path), None)
            self.order.remove(int(path))
            return True, None, None
        return False, None, "unexpected"


def test_tail_safe_rewrite_deletes_surplus_baseline_rows():
    # Sheet: baseline rows 1-3 (from the snapshot) + row 10 appended afterwards.
    sheet = FakeSheety([
        {"id": 1, "task": "a"}, {"id": 2, "task": "b"}, {"id": 3, "task": "c"}, {"id": 10, "task": "new"},
    ])
    # The rewrite now has two rows (one task was deleted).
    rows = [{"row_dict": {"task": "a"}, "sheety_id": 1}, {"row_dict": {"task": "c"}, "sheety_id": 3}]
    result = _rewrite_sheet_rows(rows, [1, 2, 3], "logs", sheet, None, {})
    assert result is not None
    assert [r["sheety_id"] for r in result] == [1, 2]
    assert sheet.order == [1, 2, 10]  # surplus baseline row 3 deleted, appended row 10 untouched
    assert sheet.rows[2]["task"] == "c"
    assert ("DELETE", "3") in sheet.calls
