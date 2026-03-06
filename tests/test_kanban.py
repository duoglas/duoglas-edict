"""tests for scripts/kanban_update.py"""

import json, pathlib, sys

# Ensure scripts/ is importable
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import kanban_update as kb


def test_create_and_get(tmp_path):
    """kanban create + get round-trip."""
    tasks_file = tmp_path / "tasks_source.json"
    tasks_file.write_text("[]")

    # Patch TASKS_FILE
    original = kb.TASKS_FILE
    kb.TASKS_FILE = tasks_file
    try:
        kb.cmd_create(
            "TEST-001", "测试任务创建和查询功能验证", "Inbox", "工部", "工部尚书"
        )
        tasks = json.loads(tasks_file.read_text())
        assert any(t.get("id") == "TEST-001" for t in tasks)
        t = next(t for t in tasks if t["id"] == "TEST-001")
        assert t["title"] == "测试任务创建和查询功能验证"
        assert t["state"] == "Inbox"
        assert t["org"] == "工部"
    finally:
        kb.TASKS_FILE = original


def test_move_state(tmp_path):
    """kanban move changes task state."""
    tasks_file = tmp_path / "tasks_source.json"
    tasks_file.write_text(
        json.dumps([{"id": "T-1", "title": "test", "state": "Inbox"}])
    )

    original = kb.TASKS_FILE
    kb.TASKS_FILE = tasks_file
    try:
        kb.cmd_state("T-1", "Doing")
        tasks = json.loads(tasks_file.read_text())
        assert tasks[0]["state"] == "Doing"
    finally:
        kb.TASKS_FILE = original


def test_block_and_unblock(tmp_path):
    """kanban block/unblock round-trip."""
    tasks_file = tmp_path / "tasks_source.json"
    tasks_file.write_text(
        json.dumps([{"id": "T-2", "title": "blocker test", "state": "Doing"}])
    )

    original = kb.TASKS_FILE
    kb.TASKS_FILE = tasks_file
    try:
        kb.cmd_block("T-2", "等待依赖")
        tasks = json.loads(tasks_file.read_text())
        assert tasks[0]["state"] == "Blocked"
        assert tasks[0]["block"] == "等待依赖"
    finally:
        kb.TASKS_FILE = original


def test_progress_updates_heartbeat_not_effective_progress(tmp_path):
    tasks_file = tmp_path / "tasks_source.json"
    tasks_file.write_text(
        json.dumps(
            [
                {
                    "id": "T-3",
                    "title": "progress test",
                    "state": "Doing",
                    "org": "执行中",
                    "updatedAt": "2026-03-06T00:00:00Z",
                    "_scheduler": {
                        "lastProgressAt": "2026-03-06T00:00:00Z",
                        "retryCount": 1,
                        "escalationLevel": 1,
                    },
                }
            ]
        )
    )

    original = kb.TASKS_FILE
    kb.TASKS_FILE = tasks_file
    try:
        kb.cmd_progress("T-3", "正在整理证据", "步骤A🔄|步骤B")
        tasks = json.loads(tasks_file.read_text())
        task = tasks[0]
        sched = task.get("_scheduler", {})

        assert sched.get("lastProgressAt") == "2026-03-06T00:00:00Z"
        assert sched.get("retryCount") == 1
        assert sched.get("escalationLevel") == 1
        assert isinstance(sched.get("lastHeartbeatAt"), str)

        progress_log = task.get("progress_log", [])
        assert len(progress_log) == 1
        assert progress_log[0].get("kind") == "heartbeat"
    finally:
        kb.TASKS_FILE = original


def test_progress_dedup_within_window(tmp_path):
    tasks_file = tmp_path / "tasks_source.json"
    tasks_file.write_text(
        json.dumps(
            [
                {
                    "id": "T-4",
                    "title": "progress dedup test",
                    "state": "Doing",
                    "org": "执行中",
                    "updatedAt": "2026-03-06T00:00:00Z",
                    "progress_log": [
                        {
                            "at": "2026-03-06T01:00:00Z",
                            "agent": "",
                            "kind": "heartbeat",
                            "text": "重复心跳",
                            "todos": [
                                {"id": "1", "title": "同步", "status": "in-progress"}
                            ],
                            "state": "Doing",
                            "org": "执行中",
                        }
                    ],
                }
            ]
        )
    )

    original_file = kb.TASKS_FILE
    original_now_iso = kb.now_iso
    kb.TASKS_FILE = tasks_file
    kb.now_iso = lambda: "2026-03-06T01:01:00Z"
    try:
        kb.cmd_progress("T-4", "重复心跳", "同步🔄")
        task = json.loads(tasks_file.read_text())[0]
        assert len(task.get("progress_log", [])) == 1
    finally:
        kb.TASKS_FILE = original_file
        kb.now_iso = original_now_iso
