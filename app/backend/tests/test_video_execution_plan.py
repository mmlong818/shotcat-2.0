from app.schemas.studio.shots import ActionBeatPhaseRead, ShotPromptCameraInfo, ShotVideoPromptPackRead
from app.services.studio.generation.video.execution_plan import (
    build_video_execution_plan,
    enrich_prompt_with_execution_plan,
)


def _pack() -> ShotVideoPromptPackRead:
    return ShotVideoPromptPackRead(
        shot_id="shot-1",
        title="推门进入",
        shot_description="角色推门进入走廊，发现异常后停住脚步。",
        action_beats=["角色推门进入走廊", "角色发现异常", "角色停住脚步看向前方"],
        action_beat_phases=[
            ActionBeatPhaseRead(text="角色推门进入走廊", phase="trigger"),
            ActionBeatPhaseRead(text="角色发现异常", phase="peak"),
            ActionBeatPhaseRead(text="角色停住脚步看向前方", phase="aftermath"),
        ],
        dialogue_summary="角色：有人吗？",
        narrative_function="从探索转为警觉",
        sound_effects="门轴轻响，脚步在走廊里回声",
        camera=ShotPromptCameraInfo(
            camera_shot="MS",
            angle="EYE_LEVEL",
            movement="DOLLY_IN",
            duration=6,
        ),
    )


def test_execution_plan_covers_full_duration_and_assigns_reference_roles() -> None:
    plan = build_video_execution_plan(
        pack=_pack(),
        reference_mode="first_last_key",
        images=["first-file", "last-file", "key-file"],
    )

    assert plan.generation_path == "multi_reference_i2v"
    assert plan.timeline[0].start_s == 0
    assert plan.timeline[-1].end_s == 6
    assert all(left.end_s == right.start_s for left, right in zip(plan.timeline, plan.timeline[1:], strict=False))
    assert [item.role for item in plan.references] == ["start", "end", "key_state"]
    assert "严格承接首帧" in plan.start_state
    assert "自然抵达尾帧" in plan.end_state
    assert "同期对白" in plan.timeline[0].audio
    assert "不默认添加背景音乐" in plan.audio_approach


def test_key_frame_plan_warns_that_key_frame_is_not_start_frame() -> None:
    plan = build_video_execution_plan(pack=_pack(), reference_mode="key", images=["key-file"])

    assert plan.references[0].role == "key_state"
    assert any("不应被模型误当作 0 秒首帧" in item for item in plan.warnings)


def test_execution_plan_is_added_to_prompt_only_once() -> None:
    plan = build_video_execution_plan(pack=_pack(), reference_mode="text_only", images=[])
    first = enrich_prompt_with_execution_plan(rendered_prompt="原始提示词", plan=plan)
    second = enrich_prompt_with_execution_plan(rendered_prompt=first, plan=plan)

    assert first == second
    assert first.count("视频执行计划（完整覆盖") == 1
