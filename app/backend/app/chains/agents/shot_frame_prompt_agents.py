"""镜头分镜首帧/尾帧/关键帧提示词生成 Agent：根据镜头信息生成对应帧的画面提示词。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase, _extract_json_from_text
from app.schemas.skills.shot_frame_prompt import ShotFramePromptResult


def _prepare_shot_frame_input(input_dict: dict[str, Any]) -> dict[str, Any]:
    """将 input_dict 转为 prompt 模板所需格式，mood_tags 转为字符串。"""
    out = dict(input_dict)
    if "mood_tags" in out and isinstance(out["mood_tags"], list):
        out["mood_tags"] = ", ".join(str(t) for t in out["mood_tags"])
    else:
        out.setdefault("mood_tags", "")
    if "action_beats" in out and isinstance(out["action_beats"], list):
        out["action_beats"] = "；".join(str(item) for item in out["action_beats"] if str(item).strip())
    else:
        out.setdefault("action_beats", "")
    for key in (
        "visual_style",
        "style",
        "unify_style",
        "camera_shot",
        "angle",
        "movement",
        "atmosphere",
        "shot_description",
        "vfx_type",
        "vfx_note",
        "duration",
        "scene_id",
        "dialog_summary",
        "action_beats",
        "action_beat_phases",
        "selected_action_beat_phase",
        "selected_action_beat_text",
        "character_context",
        "scene_context",
        "prop_context",
        "subject_priority",
        "previous_shot_title",
        "previous_shot_script_excerpt",
        "previous_shot_end_state",
        "next_shot_title",
        "next_shot_script_excerpt",
        "next_shot_start_goal",
        "continuity_guidance",
        "composition_anchor",
        "screen_direction_guidance",
        "frame_specific_guidance",
        "director_command_summary",
        "art_direction",
        "retry_guidance",
    ):
        if key not in out or out[key] is None:
            out[key] = ""
    if isinstance(out.get("unify_style"), bool):
        out["unify_style"] = "是" if out["unify_style"] else "否"
    out.setdefault("title", "")
    return out


_SHOT_FRAME_INPUT_VARS = [
    "script_excerpt",
    "title",
    "visual_style",
    "style",
    "unify_style",
    "camera_shot",
    "angle",
    "movement",
    "atmosphere",
    "shot_description",
    "mood_tags",
    "vfx_type",
    "vfx_note",
    "duration",
    "scene_id",
    "dialog_summary",
    "action_beats",
    "action_beat_phases",
    "selected_action_beat_phase",
    "selected_action_beat_text",
    "character_context",
    "scene_context",
    "prop_context",
    "subject_priority",
    "previous_shot_title",
    "previous_shot_script_excerpt",
    "previous_shot_end_state",
    "next_shot_title",
    "next_shot_script_excerpt",
    "next_shot_start_goal",
    "continuity_guidance",
    "composition_anchor",
    "screen_direction_guidance",
    "frame_specific_guidance",
    "director_command_summary",
    "art_direction",
    "retry_guidance",
]

_FRAME_FOCUS = {
    "首帧": "生成单张静态图片：只描述这一帧画面内可见的初始构图、主体状态、场景可视范围和光线，不写镜头开始、运动过程或后续变化。",
    "尾帧": "生成单张静态图片：只描述这一帧画面内可见的稳定构图、主体停留状态、视线方向和场景可视范围，不写镜头结束、运动过程或后续变化。",
    "关键帧": "生成单张静态图片：只描述这一帧最有代表性的静态画面状态、构图重心、主体姿态、场景可视范围和光线，不写整个动作过程。",
}

_SHOT_FRAME_TEMPLATE = """你是一名专业图像生成提示词设计师，需要为同一项目中的镜头生成**{frame_name}完整画面 Prompt**。

你的任务是生成“完整画面 Prompt”，用于生成该镜头的关键帧或指定帧。Prompt 必须是一段流畅的画面描述，只描述这一张图片画面内真实可见的内容，供后续系统继续拼接图片映射说明。

## 强约束
1. 必须继承项目级画面表现形式与题材风格：{visual_style} / {style}
2. 项目是否要求统一风格：{unify_style}
3. 若镜头信息不足，优先向项目风格与已确认实体设定收敛，不要自由发散到其他风格
4. 当前镜头已确认的角色、场景、道具名称必须原样保留，不得翻译、不得改名、不得替换为同义词
5. 不得输出“图1/图2”、不得输出“## 图片内容说明”；可以用自然语言写清角色、场景、道具在当前画面里的对应关系，但不要写技术性图片编号
6. 输出必须是完整画面 Prompt：用于生成该镜头的关键帧，必须把【景别、视角、主体外貌与姿态、场景环境、光影、色彩、构图、质感】融合在一段流畅描述中
7. 这是单张图片提示词，不是视频提示词；不得写运镜、镜头运动、时间推进、动作过程、变化过程、镜头开始/结束、下一秒会发生什么
8. 只输出一个 JSON 对象：{{"prompt": "你的提示词内容"}}，不要输出其他文字
9. 当前帧关注重点：{frame_focus}
10. 主体优先级建议：{subject_priority}
11. 不要为了“写全信息”而平均罗列所有角色和道具；优先突出画面内可见的主角色、主场景和关键对象，其余元素仅在画面中确实可见时再进入提示词
12. 如果下面提供了“修正要求”，必须逐条满足后再输出最终结果
13. 必须明确镜头朝向、机位方向或观看方向，例如从校门外看向校内、沿走廊纵深看向尽头、从教室后排看向黑板；不要只写抽象场景
14. 必须明确场景可视范围：画面中能看到哪些区域、边界到哪里、前景/中景/背景分别是什么；不要牵扯画面外、看不见的区域或不可见事件
15. 若存在上一镜头/下一镜头信息，只能用于统一可见空间方向、左右轴线、角色朝向和场景材质；不得在提示词中写“上一镜头/下一镜头”，不得写承接动作或未来变化
16. 尽量明确主体在画面中的相对位置、朝向、静态姿态和视线落点，减少构图和轴线突变
17. 若提供了构图与空间锚点建议，应落实为静态构图、画面边界、视觉重心和可见空间层次
18. 若提供了朝向与视线建议，应保持人物左右关系、视线落点与反打轴线稳定，不要无故翻转
18.1 若机位角度是 OVER_SHOULDER 或原文含过肩视角，优先改写为稳定平视或轻侧面双人关系，不要使用明显前景肩部遮挡
19. 若提供了当前帧专项建议，只提取其中能静态可视化的部分，不要照搬动作过程、运动阶段或视频调度说明
20. 若提供了导演指令摘要，只提取其中能静态可视化的构图、主体、朝向、场景和风格要求，不要输出“导演指令”“必须/优先”等调度话术
21. 禁止使用这些视频化表达：运镜、推进、拉远、跟拍、横摇、纵摇、移动、缓缓、逐渐、正在变化、动作链、后续、下一镜头、上一镜头、镜头开始、镜头结束、画面外、不可见区域
21.1 禁止使用肩部、肩背、借肩、前景肩部遮挡等构图；这类提示会导致生图错乱。需要表达人物关系时，改用横向构图、高角度构图、平视轻侧面、双人同框、前后景距离或左右站位
22. 若提供了艺术指导统筹，必须让最终画面同时符合剧情、项目风格、角色特征和场景质感，但只写当前图片里可见的内容
23. 若镜头补充描述中包含参考图关系，必须把它转化为画面描述里的实体对应关系，例如哪个角色、哪个场景、哪个道具应保持一致；不要输出图片编号或引用清单
24. 推荐组织顺序：景别与视角 -> 镜头朝向/观看方向 -> 场景可视范围与前中后景 -> 可见主体外貌与姿态/关键对象 -> 光影与色彩 -> 构图 -> 质感与风格
25. 不要输出分项标题，不要写“包含：景别、视角……”，不要写说明文字；这些要素必须自然融合在同一段 prompt 中
26. 如果没有角色，主体外貌与姿态应替换为画面主体物、建筑、空间结构、陈设或道具的外观与状态；不要为了满足字段而添加人物
27. 角色若会通过参考图参与图生图，提示词不要描述角色穿什么；参考图会负责锁定服装。只有没有角色参考图，或剧本/镜头明确把服装作为剧情信息、身份信息或动作焦点时，才写服装
28. 不要按场景常识给角色强加随身物件，例如书包、背包、手机、雨伞、购物袋等；只有当前镜头动作拍点明确使用、画面内必须看见、或提供了对应道具参考图时，才写入这些物件
29. 把“已确认实体上下文”视为不可漂移的身份锚点，把镜头补充描述中的“角色当前状态”视为本镜可变状态；不得用本镜姿态、表情或位置改写角色固定身份，也不得把资产背景故事硬塞进画面
30. 场景上下文负责固定材质与整体结构；镜头补充描述中的“固定场景结构、观看方向、可视范围”负责当前机位。门窗、通道、家具和关键道具的相对位置不得改变，不得为了构图丰富虚构第二套空间
31. 镜头补充描述中的“镜间关系”只用于选择动作匹配、视线匹配或视觉重心，不得把“切换、转场、承接、匹配”等关系说明原样写入最终提示词
32. 必须服从角色 visibility：人物背对镜头、面部不可见或被遮挡时，不得描述其眼神、瞳孔、嘴角或具体面部表情；LS/ELS 大景别不得依赖细微眼神、皮肤、泪痕等不可辨认细节
33. 只写实际可见角色和对象。被前景、建筑或其他人物遮挡的部位不得同时被描述为清晰可见；若可见范围与角色状态冲突，以更保守的实际可见范围为准

## 镜头信息
剧本摘录：{script_excerpt}
镜头标题：{title}
镜头补充描述：{shot_description}
景别：{camera_shot}
机位角度：{angle}
运镜参数（仅供判断静态构图，不得写成运动）：{movement}
氛围：{atmosphere}
情绪标签：{mood_tags}
视效：{vfx_type} - {vfx_note}
时长：{duration}秒
对白摘要：{dialog_summary}
动作拍点：{action_beats}
动作拍点阶段：{action_beat_phases}
当前帧优先消费阶段：{selected_action_beat_phase}
当前帧主拍点：{selected_action_beat_text}

## 已确认实体上下文
角色：{character_context}
场景：{scene_context}
道具：{prop_context}

## 相邻镜头空间参考（只用于统一可见空间、方向、材质和轴线，不得写入动作承接或未来变化）
上一镜头标题：{previous_shot_title}
上一镜头剧本摘录：{previous_shot_script_excerpt}
上一镜头结尾状态：{previous_shot_end_state}
下一镜头标题：{next_shot_title}
下一镜头剧本摘录：{next_shot_script_excerpt}
下一镜头起始目标：{next_shot_start_goal}
连续性建议：{continuity_guidance}
构图与空间锚点：{composition_anchor}
朝向与视线建议：{screen_direction_guidance}
当前帧专项建议：{frame_specific_guidance}
导演指令摘要：{director_command_summary}

## 艺术指导统筹
{art_direction}

修正要求：{retry_guidance}

## 输出（仅 {frame_name} 基础提示词，JSON：{{"prompt": "..."}}）
"""

def _build_frame_template(frame_name: str) -> str:
    return (
        _SHOT_FRAME_TEMPLATE.replace("{frame_name}", frame_name)
        .replace("{frame_focus}", _FRAME_FOCUS[frame_name])
    )


_FIRST_FRAME_TEMPLATE = _build_frame_template("首帧")
_LAST_FRAME_TEMPLATE = _build_frame_template("尾帧")
_KEY_FRAME_TEMPLATE = _build_frame_template("关键帧")

SHOT_FIRST_FRAME_PROMPT = PromptTemplate(input_variables=_SHOT_FRAME_INPUT_VARS, template=_FIRST_FRAME_TEMPLATE)
SHOT_LAST_FRAME_PROMPT = PromptTemplate(input_variables=_SHOT_FRAME_INPUT_VARS, template=_LAST_FRAME_TEMPLATE)
SHOT_KEY_FRAME_PROMPT = PromptTemplate(input_variables=_SHOT_FRAME_INPUT_VARS, template=_KEY_FRAME_TEMPLATE)


class ShotFirstFramePromptAgent(AgentBase[ShotFramePromptResult]):
    """镜头首帧提示词生成 Agent，输出可写入 ShotDetail.first_frame_prompt。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return SHOT_FIRST_FRAME_PROMPT

    @property
    def output_model(self) -> type[ShotFramePromptResult]:
        return ShotFramePromptResult

    def format_output(self, raw: str) -> ShotFramePromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ShotFramePromptResult(prompt=raw.strip())
        if isinstance(data, dict) and "prompt" in data:
            return ShotFramePromptResult(prompt=str(data["prompt"]).strip())
        return ShotFramePromptResult(prompt=raw.strip())

    def extract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)


class ShotLastFramePromptAgent(AgentBase[ShotFramePromptResult]):
    """镜头尾帧提示词生成 Agent，输出可写入 ShotDetail.last_frame_prompt。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return SHOT_LAST_FRAME_PROMPT

    @property
    def output_model(self) -> type[ShotFramePromptResult]:
        return ShotFramePromptResult

    def format_output(self, raw: str) -> ShotFramePromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ShotFramePromptResult(prompt=raw.strip())
        if isinstance(data, dict) and "prompt" in data:
            return ShotFramePromptResult(prompt=str(data["prompt"]).strip())
        return ShotFramePromptResult(prompt=raw.strip())

    def extract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)


class ShotKeyFramePromptAgent(AgentBase[ShotFramePromptResult]):
    """镜头关键帧提示词生成 Agent，输出可写入 ShotDetail.key_frame_prompt。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return SHOT_KEY_FRAME_PROMPT

    @property
    def output_model(self) -> type[ShotFramePromptResult]:
        return ShotFramePromptResult

    def format_output(self, raw: str) -> ShotFramePromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ShotFramePromptResult(prompt=raw.strip())
        if isinstance(data, dict) and "prompt" in data:
            return ShotFramePromptResult(prompt=str(data["prompt"]).strip())
        return ShotFramePromptResult(prompt=raw.strip())

    def extract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)
