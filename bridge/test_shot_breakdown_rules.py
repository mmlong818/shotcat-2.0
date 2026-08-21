from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

BRIDGE_DIR = Path(__file__).resolve().parent
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

import shot_breakdown
import pipeline_server


def _good_shots() -> list[dict]:
    """构造满足连续性与原文覆盖规则的最小标准分镜序列。"""
    base = {
        "scene": "旧宅客厅",
        "time": "夜",
        "space": "内",
        "angle": "EYE_LEVEL",
        "movement": "STATIC",
        "focal_length": "50mm标准",
        "composition": "三分法",
        "scene_geometry": "旧宅客厅为狭长矩形，木门固定在右后方，旧桌固定在左侧墙边。",
        "viewing_direction": "从客厅入口沿纵深看向右后方木门。",
        "visible_range": "前景为入口门框，中景为旧桌与周诚，背景止于右后方木门。",
        "spatial_anchor": "木门在画面右后方，旧桌在左侧；周诚始终站在桌旁。",
        "screen_direction": "周诚位于画面左侧面向右侧木门，视线落向门把手。",
        "character_states": [{
            "name": "周诚·成年时期",
            "location": "旧桌左侧",
            "posture": "站立",
            "facing": "身体朝向右后方木门",
            "gaze": "门把手",
            "visibility": "侧脸与上半身清晰可见",
        }],
        "transition_from_previous": "直接切换；以旧宅入口为视觉落点；建立场景空间。",
        "narrative_function": "建立旧宅空间与人物警惕状态。",
        "atmosphere": "压抑、安静",
        "sfx": "木门轻响",
        "reference_relations": "场景参考锁定门与旧桌的位置；角色参考锁定周诚外貌。",
        "dialogues": [],
        "duration": 4,
        "characters": ["周诚·成年时期"],
        "props": [],
    }
    return [
        {
            **base,
            "title": "旧宅空间建立",
            "script_content": "周诚走进旧宅。",
            "camera_shot": "LS",
            "action": "周诚从门口进入，在旧桌左侧停下。",
            "action_beats": ["周诚进入旧宅", "在旧桌左侧停下"],
            "description": "沿客厅纵深看向右后方木门，周诚停在左侧旧桌旁。",
            "character_states": copy.deepcopy(base["character_states"]),
            "continuity_from_previous": "本场首镜，建立门、旧桌和周诚的空间关系。",
        },
        {
            **base,
            "title": "周诚听见门响",
            "script_content": "身后的门忽然响了。",
            "camera_shot": "CU",
            "action": "周诚停在旧桌旁，目光转向右后方木门。",
            "action_beats": ["周诚闻声停住", "目光落向木门"],
            "description": "近景取周诚紧绷的侧脸，右后方木门仍在视线方向内。",
            "character_states": copy.deepcopy(base["character_states"]),
            "continuity_from_previous": "保持周诚在旧桌左侧的位置，以门响触发视线从前方转向右后方。",
            "transition_from_previous": "反应切换；匹配木门声与周诚转向门把手的视线；把异响转成悬念。",
            "narrative_function": "用反应镜头把环境异响转成悬念。",
        },
        {
            **base,
            "title": "门把手落点",
            "script_content": "",
            "camera_shot": "ECU",
            "action": "空镜：右后方木门把手轻微下压。",
            "action_beats": ["空镜：木门把手轻微下压"],
            "description": "特写木门把手，背景左侧虚化保留旧桌方向。",
            "continuity_from_previous": "顺着周诚向右的视线切到木门把手，延续同一观看方向。",
            "characters": [],
            "character_states": [],
            "screen_direction": "沿周诚由左向右的视线看向右后方木门。",
            "transition_from_previous": "视线匹配；匹配周诚向右的视线与门把手位置；揭示悬念对象。",
            "narrative_function": "给出悬念对象的信息落点。",
        },
    ]


def test_reference_rules_are_present_in_generation_and_review_prompts() -> None:
    """防止后续精简提示词时丢失本次引入的核心分镜方法。"""
    for phrase in ("三阶段", "scene_geometry", "character_states", "transition_from_previous", "180 度轴线", "30 度规则", "正反打"):
        assert phrase in shot_breakdown.SYS
    assert "空间连续性" in shot_breakdown.REVIEW_SYS
    assert "状态与场景锚定" in shot_breakdown.REVIEW_SYS
    assert "不要添加原文没有的剧情" in shot_breakdown.REVIEW_SYS


def test_model_enum_labels_are_normalized_to_pure_codes() -> None:
    """模型即使返回“代码 + 中文名”，也不应被质量闸误判为无效枚举。"""
    normalized = shot_breakdown._normalize_shots([
        {
            "camera_shot": "LS 远景",
            "angle": "EYE_LEVEL 平视",
            "movement": "STATIC 固定",
            "focal_length": "50mm 标准镜头",
            "composition": "三分法构图",
            "time": "夜景",
            "space": "室内",
        }
    ])[0]

    assert normalized["camera_shot"] == "LS"
    assert normalized["angle"] == "EYE_LEVEL"
    assert normalized["movement"] == "STATIC"
    assert normalized["focal_length"] == "50mm标准"
    assert normalized["composition"] == "三分法"
    assert normalized["time"] == "夜"
    assert normalized["space"] == "内"


def test_black_frame_is_a_valid_composition() -> None:
    """黑屏、黑场和纯黑描述应归一为合法黑场，不再触发循环修正。"""
    shots = _good_shots()
    shots[2]["composition"] = "满幅黑屏"
    normalized = shot_breakdown._normalize_shots(shots)
    issues = shot_breakdown._storyboard_quality_issues(
        normalized,
        script="周诚走进旧宅。身后的门忽然响了。",
        scene_names={"旧宅客厅"},
        character_names={"周诚·成年时期"},
        prop_names=set(),
    )

    assert normalized[2]["composition"] == "黑场"
    assert not [item for item in issues if "构图无效" in item]
    assert "黑场是合法构图" in shot_breakdown.REVIEW_SYS


def test_pipeline_forces_utf8_for_child_process_logs(monkeypatch) -> None:
    """Pipeline 子进程必须用 UTF-8 输出，避免中文错误日志在浏览器显示成乱码。"""
    captured: dict = {}

    class FakeProcess:
        stdout: list[str] = []

        def __init__(self, *args, **kwargs) -> None:
            captured.update(kwargs)

        def wait(self) -> int:
            return 0

        def terminate(self) -> None:
            return None

        def poll(self) -> None:
            return None

    monkeypatch.setattr(pipeline_server.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(pipeline_server, "_capture_revision", lambda *args: "revision-1")
    monkeypatch.setattr(pipeline_server, "_complete_step", lambda *args: None)
    monkeypatch.setattr(pipeline_server, "_persist_jobs_locked", lambda: None)
    pipeline_server.JOBS.clear()
    pipeline_server.PROCESSES.clear()
    pipeline_server.JOBS["job-1"] = {
        "status": "queued", "log": "", "error": "", "step": "shot-breakdown", "pid": "project-1",
        "cancel_requested": False,
    }

    pipeline_server._run("job-1", "shot-breakdown", "project-1", "test-model")

    assert captured["env"]["PYTHONIOENCODING"] == "utf-8"
    assert captured["env"]["PYTHONUTF8"] == "1"
    assert pipeline_server.JOBS["job-1"]["status"] == "done"


def test_pipeline_waits_for_confirmation_and_resumes_same_job(monkeypatch) -> None:
    """退出码 42 应转为等待确认；确认后同一任务携带 --repair 自动恢复执行。"""
    marker = pipeline_server.REPAIR_MARKER + json.dumps({"count": 1, "issues": ["[P0] 镜头002 无承接"]}, ensure_ascii=False)

    class RepairRequiredProcess:
        stdout = [marker + "\n"]

        def __init__(self, *args, **kwargs) -> None:
            return None

        def wait(self) -> int:
            return 42

        def terminate(self) -> None:
            return None

        def poll(self) -> None:
            return None

    monkeypatch.setattr(pipeline_server.subprocess, "Popen", RepairRequiredProcess)
    monkeypatch.setattr(pipeline_server, "_capture_revision", lambda *args: "revision-2")
    monkeypatch.setattr(pipeline_server, "_persist_jobs_locked", lambda: None)
    pipeline_server.JOBS.clear()
    pipeline_server.PROCESSES.clear()
    pipeline_server.JOBS["job-2"] = {
        "status": "queued", "log": "", "error": "", "step": "shot-breakdown", "pid": "project-1",
        "model": "test-model", "cancel_requested": False, "issues": [], "repair_round": 0,
    }

    pipeline_server._run("job-2", "shot-breakdown", "project-1", "test-model")

    assert pipeline_server.JOBS["job-2"]["status"] == "awaiting_confirmation"
    assert pipeline_server.JOBS["job-2"]["issues"] == ["[P0] 镜头002 无承接"]

    thread_args: dict = {}

    class FakeThread:
        def __init__(self, *, target, args, daemon) -> None:
            thread_args.update({"target": target, "args": args, "daemon": daemon})

        def start(self) -> None:
            thread_args["started"] = True

    monkeypatch.setattr(pipeline_server.threading, "Thread", FakeThread)
    resumed = pipeline_server._confirm_repair("job-2")

    assert resumed is not None and resumed["status"] == "queued"
    assert thread_args["args"] == ("job-2", "shot-breakdown", "project-1", "test-model", True)
    assert thread_args["started"] is True


def test_blocking_issues_are_saved_before_waiting_for_confirmation(monkeypatch, tmp_path: Path) -> None:
    """等待确认前应保存当前镜头表，使确认后的修正轮次无需重新创作。"""
    monkeypatch.setattr(shot_breakdown, "__file__", str(tmp_path / "shot_breakdown.py"))
    issues = ["[P0] 镜头002 与同场景前镜没有明确承接"]

    with pytest.raises(SystemExit) as exc_info:
        shot_breakdown._pause_for_repair("project-1", _good_shots(), issues)

    assert exc_info.value.code == shot_breakdown.REPAIR_EXIT_CODE
    pending = json.loads((tmp_path / "shots-repair-project-1.json").read_text(encoding="utf-8"))
    assert pending["issues"] == issues
    assert len(pending["shots"]) == 3


def test_quality_gate_accepts_connected_shot_sequence() -> None:
    """连续、完整且资产名称合法的镜头序列不应产生阻断问题。"""
    shots = _good_shots()
    issues = shot_breakdown._storyboard_quality_issues(
        shots,
        script="周诚走进旧宅。身后的门忽然响了。",
        scene_names={"旧宅客厅"},
        character_names={"周诚·成年时期"},
        prop_names=set(),
    )

    assert not [item for item in issues if item.startswith("[P0]")]


def test_quality_gate_rejects_disconnected_or_invented_content() -> None:
    """未承接前镜、改写原文和使用虚构资产必须阻止覆盖旧分镜。"""
    shots = _good_shots()
    shots[1]["continuity_from_previous"] = ""
    shots[1]["script_content"] = "门好像响了。"
    shots[1]["props"] = ["不存在的手机"]

    issues = shot_breakdown._storyboard_quality_issues(
        shots,
        script="周诚走进旧宅。身后的门忽然响了。",
        scene_names={"旧宅客厅"},
        character_names={"周诚·成年时期"},
        prop_names=set(),
    )

    assert any("没有明确承接" in item for item in issues)
    assert any("未逐字覆盖完整剧本" in item for item in issues)
    assert any("未入库道具" in item for item in issues)


def test_quality_gate_rejects_scene_drift_and_unmotivated_character_state_change() -> None:
    """同场景结构漂移、无动作依据的人物位置变化必须进入定向修正。"""
    shots = _good_shots()
    shots[1]["scene_geometry"] = "旧宅客厅为方形，木门固定在左前方，旧桌在右侧。"
    shots[1]["character_states"][0]["location"] = "木门右侧"
    shots[1]["action"] = "周诚站在原地，目光落向木门。"
    shots[1]["action_beats"] = ["周诚闻声停住", "目光落向木门"]

    issues = shot_breakdown._storyboard_quality_issues(
        shots,
        script="周诚走进旧宅。身后的门忽然响了。",
        scene_names={"旧宅客厅"},
        character_names={"周诚·成年时期"},
        prop_names=set(),
    )

    assert any("scene_geometry 不一致" in item for item in issues)
    assert any("未发生明确动作却改变状态：location" in item for item in issues)


def test_continuity_truth_stabilizer_inherits_geometry_and_unchanged_character_state() -> None:
    """模型措辞漂移不应进入数据库：代码应继承场景首镜结构和前镜未变角色状态。"""
    shots = _good_shots()
    shots[1]["scene_geometry"] = "另一套互相矛盾的空间结构"
    shots[1]["character_states"][0]["location"] = "木门右侧"
    shots[1]["character_states"][0]["posture"] = "坐下"
    shots[1]["action"] = "周诚站在原地，目光落向木门。"
    shots[1]["action_beats"] = ["周诚闻声停住", "目光落向木门"]

    stabilized = shot_breakdown._stabilize_continuity_truth(shots)

    assert stabilized[1]["scene_geometry"] == stabilized[0]["scene_geometry"]
    assert stabilized[1]["character_states"][0]["location"] == "旧桌左侧"
    assert stabilized[1]["character_states"][0]["posture"] == "站立"


def test_continuity_truth_stabilizer_keeps_explicit_character_movement() -> None:
    """原文或动作明确发生位移时，角色状态更新必须保留。"""
    shots = _good_shots()
    shots[1]["action"] = "周诚从旧桌左侧走到木门旁。"
    shots[1]["action_beats"] = ["周诚走到木门旁"]
    shots[1]["character_states"][0]["location"] = "木门旁"

    stabilized = shot_breakdown._stabilize_continuity_truth(shots)

    assert stabilized[1]["character_states"][0]["location"] == "木门旁"


def test_quality_gate_requires_visible_character_state_mapping() -> None:
    """每个可见角色都必须具有逐镜状态，空镜和黑场仍可不含角色状态。"""
    shots = _good_shots()
    shots[1]["character_states"] = []

    issues = shot_breakdown._storyboard_quality_issues(
        shots,
        script="周诚走进旧宅。身后的门忽然响了。",
        scene_names={"旧宅客厅"},
        character_names={"周诚·成年时期"},
        prop_names=set(),
    )

    assert any("character_states 未与可见角色逐一对应" in item for item in issues)


def test_description_keeps_director_design_for_frame_generation() -> None:
    """结构化镜头设计必须完整进入 ShotDetail.description，而不是只剩动作摘要。"""
    description = shot_breakdown._build_shot_description(_good_shots()[1])

    assert "空间锚点：木门在画面右后方" in description
    assert "固定场景结构：旧宅客厅为狭长矩形" in description
    assert "角色当前状态：" in description
    assert "镜间关系：反应切换" in description
    assert "人物调度与轴线：周诚位于画面左侧面向右侧木门" in description
    assert "前镜承接：保持周诚在旧桌左侧的位置" in description
    assert "构图：三分法；50mm标准" in description
    assert "叙事功能：用反应镜头把环境异响转成悬念" in description


def test_run_persists_source_director_design_and_structured_dialogue(monkeypatch, tmp_path: Path) -> None:
    """两轮结果通过质量闸后，应把原文、导演设计与对白关系分别写入正确的服务端字段。"""
    shots = _good_shots()
    shots[1]["dialogues"] = [
        {
            "speaker": "周诚·成年时期",
            "target": "",
            "text": "谁在那里？",
            "mode": "DIALOGUE",
        }
    ]
    model_calls: list[dict] = []
    requests: list[tuple[str, str, dict | None]] = []

    def fake_items(path: str) -> list[dict]:
        if path.startswith("/studio/chapters"):
            return [{"id": "chapter-1", "index": 1, "raw_text": "周诚走进旧宅。身后的门忽然响了。"}]
        if path.startswith("/studio/entities/scene"):
            return [{"id": "scene-1", "name": "旧宅客厅", "description": "木门、旧桌与狭长客厅"}]
        if path.startswith("/studio/entities/character"):
            return [{"id": "char-1", "name": "周诚·成年时期", "description": "成年周诚"}]
        if path.startswith("/studio/entities/prop"):
            return []
        if path.startswith("/studio/shots"):
            return []
        raise AssertionError(f"unexpected path: {path}")

    def fake_chat_json(system: str, user: str, **kwargs) -> dict:
        model_calls.append({"system": system, "user": user, **kwargs})
        return {"shots": copy.deepcopy(shots)}

    def fake_req(method: str, path: str, body=None, timeout: int = 30):
        requests.append((method, path, copy.deepcopy(body)))
        if method == "GET" and path.endswith("/brain?status=confirmed"):
            return 200, {"data": [{
                "category": "style",
                "title": "视觉基调",
                "content": "全片采用低饱和冷色，回忆段落除外。",
            }]}
        return 201, {}

    monkeypatch.setattr(shot_breakdown, "items", fake_items)
    monkeypatch.setattr(shot_breakdown, "chat_json", fake_chat_json)
    monkeypatch.setattr(shot_breakdown, "_req", fake_req)
    monkeypatch.setattr(shot_breakdown, "__file__", str(tmp_path / "shot_breakdown.py"))

    shot_breakdown.run("project-1", "test-model")

    assert len(model_calls) == 2
    assert all("全片采用低饱和冷色，回忆段落除外。" in call["user"] for call in model_calls)
    shot_body = next(body for method, path, body in requests if method == "POST" and path == "/studio/shots")
    assert shot_body["script_excerpt"] == "周诚走进旧宅。"
    detail_bodies = [body for method, path, body in requests if method == "POST" and path == "/studio/shot-details"]
    assert "空间锚点：木门在画面右后方" in detail_bodies[1]["description"]
    assert detail_bodies[1]["action_beats"][-1] == "「谁在那里？」"
    dialogue_body = next(body for method, path, body in requests if method == "POST" and path == "/studio/shot-dialog-lines")
    assert dialogue_body["speaker_character_id"] == "char-1"
    assert dialogue_body["speaker_name"] == "周诚·成年时期"
    assert dialogue_body["text"] == "谁在那里？"


def test_run_lands_full_draft_before_waiting_for_repair(monkeypatch, tmp_path: Path) -> None:
    """导演校验仍有 P0 时，也必须先落地完整镜头草稿，再进入等待确认。"""
    shots = _good_shots()
    shots[1]["composition"] = "中心构图"
    requests: list[tuple[str, str, dict | None]] = []

    def fake_items(path: str) -> list[dict]:
        if path.startswith("/studio/chapters"):
            return [{"id": "chapter-1", "index": 1, "raw_text": "周诚走进旧宅。身后的门忽然响了。"}]
        if path.startswith("/studio/entities/scene"):
            return [{"id": "scene-1", "name": "旧宅客厅", "description": "木门、旧桌与狭长客厅"}]
        if path.startswith("/studio/entities/character"):
            return [{"id": "char-1", "name": "周诚·成年时期", "description": "成年周诚"}]
        if path.startswith("/studio/entities/prop") or path.startswith("/studio/shots"):
            return []
        raise AssertionError(f"unexpected path: {path}")

    def fake_req(method: str, path: str, body=None, timeout: int = 30):
        requests.append((method, path, copy.deepcopy(body)))
        return 201, {}

    monkeypatch.setattr(shot_breakdown, "items", fake_items)
    monkeypatch.setattr(shot_breakdown, "chat_json", lambda *args, **kwargs: {"shots": copy.deepcopy(shots)})
    monkeypatch.setattr(shot_breakdown, "_req", fake_req)
    monkeypatch.setattr(shot_breakdown, "__file__", str(tmp_path / "shot_breakdown.py"))

    with pytest.raises(SystemExit) as exc_info:
        shot_breakdown.run("project-1", "test-model")

    assert exc_info.value.code == shot_breakdown.REPAIR_EXIT_CODE
    landed = [body for method, path, body in requests if method == "POST" and path == "/studio/shots"]
    assert [body["index"] for body in landed] == [1, 2, 3]
    pending = json.loads((tmp_path / "shots-repair-project-1.json").read_text(encoding="utf-8"))
    assert any("镜头002" in item and "构图无效" in item for item in pending["issues"])


def test_repair_only_replaces_the_problem_shot(monkeypatch, tmp_path: Path) -> None:
    """确认修正后只能删除并重建命中的问题镜头，不能改动其他已落地镜头。"""
    pending_shots = _good_shots()
    pending_shots[1]["composition"] = "中心构图"
    repaired_shots = copy.deepcopy(pending_shots)
    repaired_shots[1]["composition"] = "三分法"
    pending_path = tmp_path / "shots-repair-project-1.json"
    pending_path.write_text(
        json.dumps({
            "shots": pending_shots,
            "issues": ["[P0] 镜头002 构图无效或使用了中心构图：中心构图"],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    requests: list[tuple[str, str, dict | None]] = []

    def fake_items(path: str) -> list[dict]:
        if path.startswith("/studio/chapters"):
            return [{"id": "chapter-1", "index": 1, "raw_text": "周诚走进旧宅。身后的门忽然响了。"}]
        if path.startswith("/studio/entities/scene"):
            return [{"id": "scene-1", "name": "旧宅客厅", "description": "木门、旧桌与狭长客厅"}]
        if path.startswith("/studio/entities/character"):
            return [{"id": "char-1", "name": "周诚·成年时期", "description": "成年周诚"}]
        if path.startswith("/studio/entities/prop"):
            return []
        if path.startswith("/studio/shots"):
            return [{"id": f"chapter-1__shot_{index:03d}", "index": index} for index in range(1, 4)]
        raise AssertionError(f"unexpected path: {path}")

    def fake_req(method: str, path: str, body=None, timeout: int = 30):
        requests.append((method, path, copy.deepcopy(body)))
        return 201, {}

    monkeypatch.setattr(shot_breakdown, "items", fake_items)
    monkeypatch.setattr(shot_breakdown, "chat_json", lambda *args, **kwargs: {"shots": copy.deepcopy(repaired_shots)})
    monkeypatch.setattr(shot_breakdown, "_req", fake_req)
    monkeypatch.setattr(shot_breakdown, "__file__", str(tmp_path / "shot_breakdown.py"))

    shot_breakdown.run("project-1", "test-model", repair=True)

    deleted = [path for method, path, _ in requests if method == "DELETE" and path.startswith("/studio/shots/")]
    landed = [body for method, path, body in requests if method == "POST" and path == "/studio/shots"]
    assert deleted == ["/studio/shots/chapter-1__shot_002"]
    assert [body["index"] for body in landed] == [2]
    assert not pending_path.exists()
