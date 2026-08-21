from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import (
    Actor,
    CameraAngle,
    CameraMovement,
    CameraShotType,
    Chapter,
    Character,
    Costume,
    DialogueLineMode,
    Project,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    ProjectStyle,
    ProjectVisualStyle,
    Prop,
    Scene,
    Shot,
    ShotCharacterLink,
    ShotDetail,
    ShotDialogLine,
    VFXType,
)
from app.services.film.shot_frame_prompt_tasks import (
    _build_continuity_state_summary,
    _validate_generated_prompt,
    build_run_args,
    normalize_frame_type,
    persist_frame_prompt,
    prompt_field_for_frame,
    read_saved_frame_prompt,
    relation_type_for_frame,
    resolve_batch_frame_prompt,
)
from app.services.studio.action_beats import infer_action_beat_sequence, pick_action_beat_for_frame


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_shot_graph(db: AsyncSession) -> None:
    project = Project(
        id="p1",
        name="项目一",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
        unify_style=True,
    )
    chapter = Chapter(id="c1", project_id="p1", index=1, title="第一章")
    prev_shot = Shot(id="s0", chapter_id="c1", index=0, title="镜头零", script_excerpt="角色沿着墙边逼近门口。")
    shot = Shot(id="s1", chapter_id="c1", index=1, title="镜头一", script_excerpt="角色推门而入。")
    next_shot = Shot(id="s2", chapter_id="c1", index=2, title="镜头二", script_excerpt="角色停下脚步，盯向走廊尽头。")
    actor = Actor(
        id="actor-1",
        name="演员甲",
        description="短发、冷峻",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    costume = Costume(
        id="costume-1",
        name="黑色风衣",
        description="修身长款、利落",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    character = Character(
        id="char-1",
        project_id="p1",
        name="主角",
        description="克制、警惕，带着压迫感",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
        actor_id="actor-1",
        costume_id="costume-1",
    )
    scene = Scene(
        id="scene-1",
        name="废弃走廊",
        description="昏暗、潮湿、狭长",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    prop = Prop(
        id="prop-1",
        name="手电筒",
        description="金属外壳，冷白光束",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    detail = ShotDetail(
        id="s1",
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        scene_id="scene-1",
        duration=5,
        atmosphere="压抑",
        mood_tags=["紧张", "克制"],
        follow_atmosphere=True,
        vfx_type=VFXType.none,
        vfx_note="无",
        description="狭长走廊里，主角谨慎前行并回头确认身后动静。",
    )
    prev_detail = ShotDetail(
        id="s0",
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.dolly_in,
        scene_id="scene-1",
        duration=4,
        description="主角贴墙缓慢逼近门口，视线紧盯前方。",
    )
    next_detail = ShotDetail(
        id="s2",
        camera_shot=CameraShotType.cu,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        scene_id="scene-1",
        duration=3,
        description="主角停住动作，神情绷紧，视线落向走廊尽头。",
    )
    line = ShotDialogLine(
        shot_detail_id="s1",
        index=0,
        text="我们到了。",
        line_mode=DialogueLineMode.dialogue,
        speaker_name="主角",
    )
    shot_character_link = ShotCharacterLink(shot_id="s1", character_id="char-1", index=0)
    scene_link = ProjectSceneLink(project_id="p1", chapter_id="c1", shot_id="s1", scene_id="scene-1")
    prop_link = ProjectPropLink(project_id="p1", chapter_id="c1", shot_id="s1", prop_id="prop-1")
    costume_link = ProjectCostumeLink(project_id="p1", chapter_id="c1", shot_id="s1", costume_id="costume-1")
    db.add_all(
        [
            project,
            chapter,
            prev_shot,
            shot,
            next_shot,
            actor,
            costume,
            character,
            scene,
            prop,
            prev_detail,
            detail,
            next_detail,
            line,
            shot_character_link,
            scene_link,
            prop_link,
            costume_link,
        ]
    )
    await db.commit()


async def _seed_fear_reaction_shot_graph(db: AsyncSession) -> None:
    project = Project(
        id="fear-p1",
        name="惊恐项目",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
        unify_style=True,
    )
    chapter = Chapter(id="fear-c1", project_id="fear-p1", index=1, title="温室")
    shot = Shot(
        id="fear-s1",
        chapter_id="fear-c1",
        index=1,
        title="惊恐镜头",
        script_excerpt="“咔嚓。”剪刀咬合的声音在安静的温室里显得格外刺耳。陆远浑身一僵，手里的修枝剪脱手掉在地上。他下意识地捂住耳朵，蹲下身，呼吸变得急促。",
    )
    detail = ShotDetail(
        id="fear-s1",
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        duration=5,
        action_beats=[
            "听到剪刀咬合声，陆远骤然僵住",
            "修枝剪脱手下坠",
            "陆远抬手捂耳，身体下沉",
            "蹲下后呼吸急促",
        ],
        description="陆远在温室里修剪枝叶，忽然被刺耳剪刀声惊到，身体僵住，手中的修枝剪脱手下坠。",
        atmosphere="压抑",
        mood_tags=["惊恐"],
        follow_atmosphere=True,
        vfx_type=VFXType.none,
        vfx_note="无",
    )
    db.add_all([project, chapter, shot, detail])
    await db.commit()


def test_normalize_frame_type_and_relation_type() -> None:
    assert normalize_frame_type(" First ") == "first"
    assert relation_type_for_frame("first") == "shot_first_frame_prompt"
    assert relation_type_for_frame("last") == "shot_last_frame_prompt"
    assert relation_type_for_frame("key") == "shot_key_frame_prompt"

    with pytest.raises(HTTPException) as exc_info:
        normalize_frame_type("middle")

    assert exc_info.value.status_code == 400


def test_action_beat_phase_inference_prefers_trigger_peak_and_aftermath() -> None:
    beats = [
        "听到剪刀咬合声，陆远骤然僵住",
        "修枝剪脱手下坠",
        "陆远抬手捂耳，身体下沉",
        "蹲下后呼吸急促",
    ]

    sequence = infer_action_beat_sequence(beats)
    first_item = pick_action_beat_for_frame("first", beats)
    key_item = pick_action_beat_for_frame("key", beats)
    last_item = pick_action_beat_for_frame("last", beats)

    assert [item.phase for item in sequence] == ["trigger", "peak", "peak", "aftermath"]
    assert first_item is not None and first_item.text == "听到剪刀咬合声，陆远骤然僵住"
    assert key_item is not None and key_item.text == "陆远抬手捂耳，身体下沉"
    assert last_item is not None and last_item.text == "蹲下后呼吸急促"


def test_prompt_quality_rejects_invisible_face_details_and_transition_language() -> None:
    prompt = (
        "LS远景平视，主角背对镜头站在走廊左侧，眼角泪痕与瞳孔清晰可见，"
        "通过视线匹配转场承接前镜；昏暗冷色侧光，前中后景纵深构图，潮湿墙面具有写实电影质感。"
    )

    issues = _validate_generated_prompt(prompt, {
        "camera_shot": "LS",
        "shot_description": '角色当前状态：[{"name": "主角", "visibility": "背面可见，面部不可见"}]',
        "character_context": "- 主角：克制、警惕",
    })

    assert any("面部在本镜不可见" in item for item in issues)
    assert any("大景别无法可靠呈现" in item for item in issues)
    assert any("混入镜间关系说明" in item for item in issues)


def test_continuity_summary_keeps_structured_geometry_and_character_state() -> None:
    description = "\n".join([
        "画面描述：周诚站在旧桌左侧。",
        "固定场景结构：木门固定在右后方，旧桌固定在左墙。",
        "观看方向：从入口看向木门。",
        "可视范围：前景入口，中景旧桌，背景木门。",
        "空间锚点：周诚位于旧桌左侧。",
        "人物调度与轴线：周诚在画面左侧面向右。",
        '角色当前状态：[{"name":"周诚","location":"旧桌左侧","posture":"站立"}]',
        "前镜承接：这一项不属于相邻画面真值摘要。",
    ])

    summary = _build_continuity_state_summary(description)

    assert "固定场景结构：木门固定在右后方" in summary
    assert "角色当前状态：" in summary
    assert "前镜承接" not in summary


@pytest.mark.asyncio
async def test_build_run_args_aggregates_dialog_and_project_style() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)

        run_args = await build_run_args(db, shot_id="s1", frame_type="first")

        assert run_args["frame_type"] == "first"
        assert run_args["shot_id"] == "s1"
        assert run_args["input"]["title"] == "镜头一"
        assert run_args["input"]["script_excerpt"] == "角色推门而入。"
        assert run_args["input"]["camera_shot"] == "MS"
        assert run_args["input"]["angle"] == "EYE_LEVEL"
        assert run_args["input"]["movement"] == "STATIC"
        assert run_args["input"]["dialog_summary"] == "主角：我们到了。"
        assert run_args["input"]["visual_style"] == ProjectVisualStyle.live_action.value
        assert run_args["input"]["style"] == ProjectStyle.real_people_city.value
        assert run_args["input"]["unify_style"] is True
        assert run_args["input"]["shot_description"] == "狭长走廊里，主角谨慎前行并回头确认身后动静。"
        assert "主角：克制、警惕，带着压迫感" in run_args["input"]["character_context"]
        assert "演员形象：演员甲（短发、冷峻）" in run_args["input"]["character_context"]
        assert "默认服装" not in run_args["input"]["character_context"]
        assert run_args["input"]["scene_context"] == "- 废弃走廊：昏暗、潮湿、狭长"
        assert run_args["input"]["prop_context"] == "- 手电筒：金属外壳，冷白光束"
        assert "costume_context" not in run_args["input"]
        assert "优先以角色 主角 作为画面主体" in run_args["input"]["subject_priority"]
        assert "优先建立场景 废弃走廊 的环境信息" in run_args["input"]["subject_priority"]
        assert "道具 手电筒 仅在进入主动作或构图焦点时重点写入" in run_args["input"]["subject_priority"]
        assert run_args["input"]["previous_shot_title"] == "镜头零"
        assert "角色沿着墙边逼近门口" in run_args["input"]["previous_shot_script_excerpt"]
        assert "场景：废弃走廊" in run_args["input"]["previous_shot_end_state"]
        assert run_args["input"]["next_shot_title"] == "镜头二"
        assert "角色停下脚步" in run_args["input"]["next_shot_script_excerpt"]
        assert "画面状态：主角停住动作" in run_args["input"]["next_shot_start_goal"]
        assert "仅参考上一镜头的可见空间方向、左右轴线、主体朝向和场景材质，不写动作承接" in run_args["input"]["continuity_guidance"]
        assert "仅参考下一镜头的可见空间方向和视觉重心，不写未来动作、变化或衔接结果" in run_args["input"]["continuity_guidance"]
        assert "可视范围应同时包含主体全貌或半身与周围关键环境，交代人物和空间关系" in run_args["input"]["composition_anchor"]
        assert "以场景 废弃走廊 作为空间锚点" in run_args["input"]["composition_anchor"]
        assert "优先锁定角色 主角 在画面内的朝向、视线和左右位置" in run_args["input"]["composition_anchor"]
        assert "优先保持人物视线水平和对视方向稳定" in run_args["input"]["screen_direction_guidance"]
        assert "存在对白时，优先保证说话者与受话者的视线关系连续" in run_args["input"]["screen_direction_guidance"]
        assert "角色 主角 的朝向与视线落点应在相邻镜头中保持延续" in run_args["input"]["screen_direction_guidance"]
        assert "首帧应优先建立静态空间、主体初始站位、镜头朝向和第一眼可见范围" in run_args["input"]["frame_specific_guidance"]
        assert "首帧只写当前图片内可见的主体状态和环境，不写后续动作、变化过程或结果" in run_args["input"]["frame_specific_guidance"]
        assert "若剧本存在连续反应链，只截取可见的静态起始姿态，不描述动作链本身" in run_args["input"]["frame_specific_guidance"]
        assert "首帧可参考上一镜头的可见空间轴线和主体朝向，但不得写上一镜头动作" in run_args["input"]["frame_specific_guidance"]
        assert "必须：若剧本存在连续反应链，只截取可见的静态起始姿态，不描述动作链本身" in run_args["input"]["director_command_summary"]
        assert "必须：与上一镜头同场景时，不要无故翻转人物面向和左右轴线" in run_args["input"]["director_command_summary"]
        assert "必须：仅参考下一镜头的可见空间方向和视觉重心，不写未来动作、变化或衔接结果" in run_args["input"]["director_command_summary"]
        assert "必须：以场景 废弃走廊 作为空间锚点" in run_args["input"]["director_command_summary"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_batch_frame_prompt_uses_saved_prompt() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        detail = await db.get(ShotDetail, "s1")
        assert detail is not None
        detail.key_frame_prompt = "已确认的关键帧提示词"
        await db.commit()

        prompt = await resolve_batch_frame_prompt(db, shot_id="s1", frame_type="key")

        assert prompt == "已确认的关键帧提示词"
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_batch_frame_prompt_falls_back_without_text_model() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)

        prompt = await resolve_batch_frame_prompt(db, shot_id="s1", frame_type="key")

        assert prompt.startswith("MS，镜头一")
        assert "狭长走廊里，主角谨慎前行并回头确认身后动静。" in prompt
        assert "角色推门而入。" in prompt
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_frame_prompt_round_trip() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)

        saved = await persist_frame_prompt(
            db,
            shot_id="s1",
            frame_type="key",
            prompt="  新生成的关键帧提示词  ",
        )
        await db.commit()

        assert saved == "新生成的关键帧提示词"
        assert await read_saved_frame_prompt(db, shot_id="s1", frame_type="key") == saved
        assert prompt_field_for_frame("key") == "key_frame_prompt"
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_provides_different_guidance_for_key_and_last_frames() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)

        key_args = await build_run_args(db, shot_id="s1", frame_type="key")
        last_args = await build_run_args(db, shot_id="s1", frame_type="last")

        assert "关键帧应锁定镜头内最具代表性的单张静态画面" in key_args["input"]["frame_specific_guidance"]
        assert "尾帧应写成单张静态图片中的稳定主体姿态" in last_args["input"]["frame_specific_guidance"]
        assert key_args["input"]["frame_specific_guidance"] != last_args["input"]["frame_specific_guidance"]
        assert "必须：关键帧应锁定镜头内最具代表性的单张静态画面，不要平均描述整个过程" in key_args["input"]["director_command_summary"]
        assert "必须：尾帧应写成单张静态图片中的稳定主体姿态、视线停留点和可见环境" in last_args["input"]["director_command_summary"]
        assert "必须：与上一镜头同场景时，不要无故翻转人物面向和左右轴线" in last_args["input"]["director_command_summary"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_requires_shot_detail() -> None:
    db, engine = await _build_session()
    async with db:
        project = Project(
            id="p1",
            name="项目一",
            description="",
            style=ProjectStyle.real_people_city,
            visual_style=ProjectVisualStyle.live_action,
        )
        chapter = Chapter(id="c1", project_id="p1", index=1, title="第一章")
        shot = Shot(id="s1", chapter_id="c1", index=1, title="镜头一")
        db.add_all([project, chapter, shot])
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await build_run_args(db, shot_id="s1", frame_type="key")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "ShotDetail not found"
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_strengthens_first_frame_for_sequential_reaction_chain() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_fear_reaction_shot_graph(db)

        run_args = await build_run_args(db, shot_id="fear-s1", frame_type="first")

        assert "当前镜头存在明显连续反应链" in run_args["input"]["frame_specific_guidance"]
        assert "首帧只保留画面内最早可见的姿态和空间关系，不写过程" in run_args["input"]["frame_specific_guidance"]
        assert "当前帧只把动作拍点“听到剪刀咬合声，陆远骤然僵住”转化为当前图片内可见的静态姿态" in run_args["input"]["frame_specific_guidance"]
        assert "必须：若剧本存在连续反应链，只截取可见的静态起始姿态，不描述动作链本身" in run_args["input"]["director_command_summary"]
        assert "当前镜头存在明显连续反应链，首帧只保留画面内最早可见的姿态和空间关系，不写过程" in run_args["input"]["director_command_summary"]
    await engine.dispose()
