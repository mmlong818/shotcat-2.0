"""镜头相关 schemas：Shot / ShotDetail / ShotDialogLine / Link 表。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.studio import (
    CameraAngle,
    CameraMovement,
    CameraShotType,
    DialogueLineMode,
    ShotFrameType,
    ShotCandidateStatus,
    ShotCandidateType,
    ShotDialogueCandidateStatus,
    ShotStatus,
    VFXType,
)


class ShotBase(BaseModel):
    id: str = Field(..., description="镜头 ID")
    chapter_id: str = Field(..., description="所属章节 ID")
    index: int = Field(..., description="镜头序号（章节内唯一）")
    title: str = Field(..., description="镜头标题")
    thumbnail: str = Field("", description="缩略图 URL/路径")
    status: ShotStatus = Field(ShotStatus.pending, description="镜头状态")
    skip_extraction: bool = Field(False, description="是否明确跳过信息提取")
    script_excerpt: str = Field("", description="剧本摘录")
    version: int = Field(1, ge=1, description="镜头记录版本")
    source_chapter_version: int = Field(1, ge=1, description="拆镜头时使用的剧本版本")
    is_stale: bool = Field(False, description="是否因上游变更而待重做")
    stale_reason: str = Field("", description="待重做原因")
    generated_video_file_id: str | None = Field(
        None,
        description="已生成视频关联的文件 ID（files.id，type=video）",
    )


class ShotExtractionSummaryRead(BaseModel):
    state: Literal[
        "not_extracted",
        "extracted_empty",
        "extracted_pending",
        "extracted_resolved",
        "skipped",
    ] = Field(..., description="镜头提取确认状态摘要")
    has_extracted: bool = Field(..., description="是否已执行过提取")
    last_extracted_at: datetime | None = Field(None, description="最近一次提取完成时间")
    asset_candidate_total: int = Field(0, description="资产候选总数")
    dialogue_candidate_total: int = Field(0, description="对白候选总数")
    pending_asset_count: int = Field(0, description="待确认资产候选数")
    pending_dialogue_count: int = Field(0, description="待确认对白候选数")


class ShotCreate(ShotBase):
    pass


class ShotUpdate(BaseModel):
    chapter_id: str | None = None
    index: int | None = None
    title: str | None = None
    thumbnail: str | None = None
    status: ShotStatus | None = None
    skip_extraction: bool | None = None
    script_excerpt: str | None = None
    generated_video_file_id: str | None = None


class ShotRead(ShotBase):
    last_extracted_at: datetime | None = Field(None, description="最近一次完成信息提取的时间")
    extraction: ShotExtractionSummaryRead = Field(..., description="镜头提取状态摘要")
    model_config = ConfigDict(from_attributes=True)


class ShotSkipExtractionUpdate(BaseModel):
    skip: bool = Field(..., description="是否明确跳过信息提取")


class ShotExtractedCandidateLinkRequest(BaseModel):
    linked_entity_id: str = Field(..., description="确认关联到的实体 ID")


class ShotExtractedCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="候选项 ID")
    shot_id: str = Field(..., description="所属镜头 ID")
    candidate_type: ShotCandidateType = Field(..., description="候选类型")
    candidate_name: str = Field(..., description="提取出的候选名称")
    candidate_status: ShotCandidateStatus = Field(..., description="候选确认状态")
    linked_entity_id: str | None = Field(None, description="已关联实体 ID")
    source: str = Field(..., description="候选来源")
    payload: dict = Field(default_factory=dict, description="候选附加信息")
    confirmed_at: datetime | None = Field(None, description="确认时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class ShotExtractedDialogueCandidateAcceptRequest(BaseModel):
    index: int | None = Field(None, description="写入对白行时使用的排序；为空则使用候选排序")
    text: str | None = Field(None, description="接受时可覆盖对白文本")
    line_mode: DialogueLineMode | None = Field(None, description="接受时可覆盖对白模式")
    speaker_name: str | None = Field(None, description="接受时可覆盖说话角色名称")
    target_name: str | None = Field(None, description="接受时可覆盖听者角色名称")


class ShotExtractedDialogueCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="对白候选项 ID")
    shot_id: str = Field(..., description="所属镜头 ID")
    index: int = Field(..., description="镜头内对白候选排序")
    text: str = Field(..., description="提取出的对白文本")
    line_mode: DialogueLineMode = Field(..., description="对白模式")
    speaker_name: str | None = Field(None, description="说话角色名称")
    target_name: str | None = Field(None, description="听者角色名称")
    candidate_status: ShotDialogueCandidateStatus = Field(..., description="对白候选确认状态")
    linked_dialog_line_id: int | None = Field(None, description="已接受后关联的对白行 ID")
    source: str = Field(..., description="候选来源")
    payload: dict = Field(default_factory=dict, description="候选附加信息")
    confirmed_at: datetime | None = Field(None, description="确认时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class ShotDetailBase(BaseModel):
    id: str = Field(..., description="镜头 ID（与 shots.id 共享主键）")
    camera_shot: CameraShotType = Field(..., description="景别")
    angle: CameraAngle = Field(..., description="机位角度")
    movement: CameraMovement = Field(..., description="运镜方式")
    scene_id: str | None = Field(None, description="关联场景 ID（可空）")
    duration: int = Field(0, description="时长（秒）")
    override_video_ratio: str | None = Field(None, description="分镜级视频比例覆盖；为空表示继承项目默认")
    mood_tags: list[str] = Field(default_factory=list, description="情绪标签")
    atmosphere: str = Field("", description="氛围描述")
    follow_atmosphere: bool = Field(True, description="是否沿用氛围")
    has_bgm: bool = Field(False, description="是否包含 BGM")
    vfx_type: VFXType = Field(VFXType.none, description="视效类型")
    vfx_note: str = Field("", description="视效说明")
    description: str = Field("", description="分镜整体描述（含画面、空间锚点、构图与连续性）")
    action_beats: list[str] = Field(default_factory=list, description="动作拍点（按时间顺序排列）")
    first_frame_prompt: str = Field(
        "",
        description="镜头分镜首帧提示词",
    )
    last_frame_prompt: str = Field(
        "",
        description="镜头分镜尾帧提示词",
    )
    key_frame_prompt: str = Field(
        "",
        description="镜头分镜关键帧提示词",
    )
    version: int = Field(1, ge=1, description="镜头设计版本")
    prompt_version: int = Field(1, ge=1, description="画面提示词版本")
    narrative_function: str = Field("", description="镜头叙事目的")
    continuity_from_previous: str = Field("", description="与前镜连续性")
    transition_from_previous: str = Field("", description="与前镜转场关系")
    sound_effects: str = Field("", description="镜头声音设计")
    reference_relations: str = Field("", description="资产引用关系")


class ShotDetailCreate(ShotDetailBase):
    pass


class ShotDetailUpdate(BaseModel):
    camera_shot: CameraShotType | None = None
    angle: CameraAngle | None = None
    movement: CameraMovement | None = None
    scene_id: str | None = None
    duration: int | None = None
    override_video_ratio: str | None = None
    mood_tags: list[str] | None = None
    atmosphere: str | None = None
    follow_atmosphere: bool | None = None
    has_bgm: bool | None = None
    vfx_type: VFXType | None = None
    vfx_note: str | None = None
    description: str | None = None
    action_beats: list[str] | None = None
    first_frame_prompt: str | None = None
    last_frame_prompt: str | None = None
    key_frame_prompt: str | None = None
    narrative_function: str | None = None
    continuity_from_previous: str | None = None
    transition_from_previous: str | None = None
    sound_effects: str | None = None
    reference_relations: str | None = None


class ShotDetailRead(ShotDetailBase):
    model_config = ConfigDict(from_attributes=True)


class ShotDialogLineBase(BaseModel):
    id: int = Field(..., description="对话行 ID")
    shot_detail_id: str = Field(..., description="所属镜头细节 ID")
    index: int = Field(0, description="行号（镜头内排序）")
    text: str = Field(..., description="台词内容")
    line_mode: DialogueLineMode = Field(DialogueLineMode.dialogue, description="对白模式")
    speaker_character_id: str | None = Field(None, description="说话角色 ID")
    target_character_id: str | None = Field(None, description="听者角色 ID")
    speaker_name: str | None = Field(None, description="说话角色名称（用于回填关联；可空）")
    target_name: str | None = Field(None, description="听者角色名称（用于回填关联；可空）")


class ShotDialogLineCreate(BaseModel):
    shot_detail_id: str
    index: int = 0
    text: str
    line_mode: DialogueLineMode = DialogueLineMode.dialogue
    speaker_character_id: str | None = None
    target_character_id: str | None = None
    speaker_name: str | None = None
    target_name: str | None = None


class ShotDialogLineUpdate(BaseModel):
    index: int | None = None
    text: str | None = None
    line_mode: DialogueLineMode | None = None
    speaker_character_id: str | None = None
    target_character_id: str | None = None
    speaker_name: str | None = None
    target_name: str | None = None


class ShotDialogLineRead(ShotDialogLineBase):
    model_config = ConfigDict(from_attributes=True)


class ProjectLinkBase(BaseModel):
    id: int = Field(..., description="关联行 ID")
    project_id: str = Field(..., description="项目 ID")
    chapter_id: str | None = Field(None, description="章节 ID（可空）")
    shot_id: str | None = Field(None, description="镜头 ID（可空）")


class ProjectAssetLinkCreate(BaseModel):
    project_id: str
    chapter_id: str | None = None
    shot_id: str | None = None
    asset_id: str


class ProjectActorLinkRead(ProjectLinkBase):
    model_config = ConfigDict(from_attributes=True)

    actor_id: str
    thumbnail: str = Field("", description="演员缩略图下载地址")


class ProjectSceneLinkRead(ProjectLinkBase):
    model_config = ConfigDict(from_attributes=True)

    scene_id: str
    thumbnail: str = Field("", description="场景缩略图下载地址")


class ProjectPropLinkRead(ProjectLinkBase):
    model_config = ConfigDict(from_attributes=True)

    prop_id: str
    thumbnail: str = Field("", description="道具缩略图下载地址")


class ProjectCostumeLinkRead(ProjectLinkBase):
    model_config = ConfigDict(from_attributes=True)

    costume_id: str
    thumbnail: str = Field("", description="服装缩略图下载地址")


class ShotFrameImageBase(BaseModel):
    id: int = Field(..., description="图片行 ID")
    shot_detail_id: str = Field(..., description="所属镜头细节 ID")
    frame_type: ShotFrameType = Field(..., description="帧类型：first/last/key")
    file_id: str | None = Field(None, description="关联的 FileItem ID（可为空，允许先创建占位）")
    width: int | None = Field(None, description="宽(px)")
    height: int | None = Field(None, description="高(px)")
    format: str = Field("png", description="格式")
    shot_version: int = Field(1, ge=1, description="生成时使用的镜头版本")
    prompt_version: int = Field(1, ge=1, description="生成时使用的提示词版本")
    asset_versions: dict[str, object] = Field(default_factory=dict, description="生成时使用的资产版本")
    is_stale: bool = Field(False, description="是否因上游变化而失效")


class ShotFrameImageCreate(BaseModel):
    shot_detail_id: str
    frame_type: ShotFrameType
    file_id: str | None = None
    width: int | None = None
    height: int | None = None
    format: str = "png"
    shot_version: int = 1
    prompt_version: int = 1
    asset_versions: dict[str, object] = Field(default_factory=dict)
    is_stale: bool = False


class ShotFrameImageUpdate(BaseModel):
    frame_type: ShotFrameType | None = None
    file_id: str | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None


class ShotFrameImageRead(ShotFrameImageBase):
    model_config = ConfigDict(from_attributes=True)


ShotLinkedAssetType = Literal["character", "prop", "scene", "costume"]


class ShotLinkedAssetItem(BaseModel):
    """按分镜聚合返回的关联资产条目（角色/道具/场景/服装）。"""

    type: ShotLinkedAssetType = Field(..., description="实体类型：character/prop/scene/costume")
    id: str = Field(..., description="实体 ID（如 character_id/prop_id/scene_id/costume_id）")
    image_id: int | None = Field(
        None,
        description="最佳缩略图对应的 image 行 ID（如 PropImage.id）；无图则为 null",
    )
    file_id: str | None = Field(
        None,
        description="最佳缩略图对应的文件 ID（files.id）；用于参考图输入；无图则为 null",
    )
    name: str = Field(..., description="实体名称")
    thumbnail: str = Field("", description="缩略图下载地址（/api/v1/studio/files/{file_id}/download）")
    reference_id: str | None = Field(None, description="已采用的稳定参考版本 ID")
    reference_version: int | None = Field(None, description="已采用的参考版本号")


class ShotFramePromptMappingRead(BaseModel):
    """关键帧提示词渲染后的图片映射关系。"""

    token: str = Field(..., description="提示词中的图片占位 token，如 图1 / 图2")
    type: ShotLinkedAssetType = Field(..., description="实体类型：character/prop/scene/costume")
    id: str = Field(..., description="实体 ID（如 character_id/prop_id/scene_id/costume_id）")
    name: str = Field(..., description="实体名称")
    file_id: str = Field(..., description="本次渲染与生成使用的文件 ID")


FrameReferenceRole = Literal["identity", "costume", "environment", "prop", "reference"]


class FrameReferenceRoleRead(BaseModel):
    """单张参考图在当前画面生成中的明确职责。"""

    token: str = Field(..., description="参考图顺序 token，如 图1")
    type: ShotLinkedAssetType = Field(..., description="参考实体类型")
    name: str = Field(..., description="参考实体名称")
    file_id: str = Field(..., description="参考图文件 ID")
    role: FrameReferenceRole = Field(..., description="职责：身份/服装/环境/道具/通用参考")
    label: str = Field(..., description="面向用户展示的职责名称")
    instruction: str = Field(..., description="该参考图约束生成结果的方式")


class FramePromptPlanRead(BaseModel):
    """画面生成前可预览的结构化计划。"""

    frame_goal: str = Field("", description="当前帧需要完成的叙事职责")
    visual_prompt: str = Field(..., description="画面主体、动作与可见环境描述")
    director_constraints: list[str] = Field(default_factory=list, description="导演级硬约束")
    continuity: list[str] = Field(default_factory=list, description="镜头承接、朝向与视线约束")
    composition: list[str] = Field(default_factory=list, description="构图与空间锚点")
    reference_roles: list[FrameReferenceRoleRead] = Field(default_factory=list, description="各参考图的职责")


class FrameGuidanceDecisionRead(BaseModel):
    """分镜帧 guidance 的保留/压缩决策结果。"""

    text: str = Field(..., description="guidance 原文")
    category: str = Field(..., description="guidance 分类，如 summary / continuity / composition / screen")
    reason_tag: str = Field("", description="简短原因标签，如 首帧保空间 / 关键帧保轴线")
    reason: str = Field(..., description="该 guidance 被保留或压缩的原因说明")


class RenderedShotFramePromptRead(BaseModel):
    """关键帧最终生成提示词渲染结果。"""

    base_prompt: str = Field(..., description="原始基础提示词（不含图片映射说明）")
    rendered_prompt: str = Field(..., description="最终提交给模型的提示词（含图片映射说明）")
    prompt_plan: FramePromptPlanRead = Field(..., description="本次画面生成的结构化执行计划")
    selected_guidance: list[str] = Field(default_factory=list, description="最终 prompt 实际保留的 guidance 列表")
    dropped_guidance: list[str] = Field(default_factory=list, description="本次渲染中被压缩掉的 guidance 列表")
    selected_guidance_details: list[FrameGuidanceDecisionRead] = Field(default_factory=list, description="最终保留 guidance 的决策详情")
    dropped_guidance_details: list[FrameGuidanceDecisionRead] = Field(default_factory=list, description="被压缩 guidance 的决策详情")
    images: list[str] = Field(default_factory=list, description="最终参考图 file_id 列表，顺序与 mappings 一致")
    mappings: list[ShotFramePromptMappingRead] = Field(
        default_factory=list,
        description="图片与实体名称的映射关系，顺序与 images 完全一致",
    )


ShotAssetOverviewSource = Literal["linked", "candidate", "both"]


class ShotAssetOverviewItem(BaseModel):
    """分镜资产总览项：统一返回已关联资产与提取候选的合并视图。"""

    key: str = Field(..., description="合并键：type:name")
    type: ShotLinkedAssetType = Field(..., description="实体类型：character/prop/scene/costume")
    name: str = Field(..., description="资产名称")
    description: str | None = Field(None, description="候选描述（来自 extraction payload）")
    thumbnail: str | None = Field(None, description="缩略图")
    file_id: str | None = Field(None, description="缩略图或参考图文件 ID")

    source: ShotAssetOverviewSource = Field(..., description="来源：linked/candidate/both")
    candidate_id: int | None = Field(None, description="候选项 ID")
    candidate_status: ShotCandidateStatus | None = Field(None, description="候选确认状态")

    linked_entity_id: str | None = Field(None, description="当前已关联实体 ID")
    linked_image_id: int | None = Field(None, description="当前已关联实体的 image 行 ID")
    is_linked: bool = Field(..., description="当前是否已关联到镜头")


class ShotAssetsOverviewSummary(BaseModel):
    linked_count: int = Field(..., description="已关联项数量")
    pending_count: int = Field(..., description="待确认候选数量")
    ignored_count: int = Field(..., description="已忽略候选数量")
    total_count: int = Field(..., description="总项数（含 ignored）")


class ShotAssetsOverviewRead(BaseModel):
    shot_id: str = Field(..., description="镜头 ID")
    skip_extraction: bool = Field(..., description="是否明确跳过提取")
    status: ShotStatus = Field(..., description="镜头流程状态")
    summary: ShotAssetsOverviewSummary = Field(..., description="总览统计")
    items: list[ShotAssetOverviewItem] = Field(default_factory=list, description="资产总览项")


class ShotPreparationLinkEntityType(str, Enum):
    character = "character"
    scene = "scene"
    prop = "prop"
    costume = "costume"


class ShotPreparationLinkRequest(BaseModel):
    project_id: str = Field(..., description="项目 ID")
    chapter_id: str = Field(..., description="章节 ID")
    entity_type: ShotPreparationLinkEntityType = Field(..., description="准备页关联的实体类型")
    linked_entity_id: str = Field(..., description="要关联的实体 ID")


class ActionBeatPhaseRead(BaseModel):
    """动作拍点的轻量阶段推断结果。"""

    text: str = Field(..., description="动作拍点原文")
    phase: Literal["trigger", "peak", "aftermath"] = Field(..., description="推断阶段：触发 / 峰值 / 收束")


class ShotPreparationStateRead(BaseModel):
    """分镜准备页聚合状态。"""

    shot: ShotRead = Field(..., description="当前镜头最新状态")
    assets_overview: ShotAssetsOverviewRead = Field(..., description="资产确认区聚合状态")
    dialogue_candidates: list[ShotExtractedDialogueCandidateRead] = Field(
        default_factory=list,
        description="当前待处理/已存在的对白候选",
    )
    saved_dialogue_lines: list[ShotDialogLineRead] = Field(
        default_factory=list,
        description="当前已保存的对白行",
    )
    pending_confirm_count: int = Field(..., description="当前仍待确认的总数量（资产 + 对白）")
    basic_info_ready: bool = Field(..., description="标题与剧本摘录是否已补齐")
    semantic_defaults_ready: bool = Field(..., description="镜头语言默认值是否已确认")
    action_beats_ready: bool = Field(..., description="动作拍点是否已确认")
    action_beats_count: int = Field(0, description="当前已确认动作拍点数量")
    action_beat_phases: list[ActionBeatPhaseRead] = Field(default_factory=list, description="当前动作拍点的阶段推断结果")
    ready_for_generation: bool = Field(..., description="当前镜头是否已完成准备，可进入后续生成")


class ShotPreparationMutationAction(str, Enum):
    link_asset_candidate = "link_asset_candidate"
    ignore_asset_candidate = "ignore_asset_candidate"
    accept_dialogue_candidate = "accept_dialogue_candidate"
    ignore_dialogue_candidate = "ignore_dialogue_candidate"
    skip_extraction = "skip_extraction"
    resume_extraction = "resume_extraction"


class ShotPreparationMutationResultRead(BaseModel):
    """准备页命令执行后的统一响应。"""

    action: ShotPreparationMutationAction = Field(..., description="本次执行的准备页动作")
    state: ShotPreparationStateRead = Field(..., description="动作完成后的最新准备页聚合状态")


class ShotPromptAssetRef(BaseModel):
    """用于提示词渲染的镜头资产引用。"""

    type: ShotLinkedAssetType = Field(..., description="资产类型")
    name: str = Field(..., description="资产名称")
    description: str = Field("", description="资产描述或提取候选描述")
    file_id: str | None = Field(None, description="可作为参考图的文件 ID")
    thumbnail: str | None = Field(None, description="缩略图")


class ShotPromptCameraInfo(BaseModel):
    """用于提示词渲染的镜头语言信息。"""

    camera_shot: str = Field("", description="景别")
    angle: str = Field("", description="机位角度")
    movement: str = Field("", description="运镜方式")
    duration: int | None = Field(None, description="镜头时长（秒）")


class ShotVideoPromptPackRead(BaseModel):
    """视频提示词渲染前的标准上下文包。"""

    shot_id: str = Field(..., description="镜头 ID")
    title: str = Field("", description="镜头标题")
    script_excerpt: str = Field("", description="剧本摘录")
    shot_description: str = Field("", description="镜头整体画面描述")
    action_beats: list[str] = Field(default_factory=list, description="动作/场景要点")
    action_beat_phases: list[ActionBeatPhaseRead] = Field(default_factory=list, description="动作拍点的阶段推断结果")
    previous_shot_summary: str = Field("", description="上一镜头摘要，用于提示词连续性约束")
    next_shot_goal: str = Field("", description="下一镜头目标，用于提示词连续性约束")
    continuity_guidance: str = Field("", description="当前镜头与相邻镜头的承接建议")
    composition_anchor: str = Field("", description="当前镜头的构图与空间锚点建议")
    screen_direction_guidance: str = Field("", description="当前镜头的人物朝向、视线与左右轴线建议")
    dialogue_summary: str = Field("", description="对白摘要")
    narrative_function: str = Field("", description="镜头叙事目的")
    sound_effects: str = Field("", description="镜头声音设计")
    has_bgm: bool = Field(False, description="是否明确要求背景音乐")
    characters: list[ShotPromptAssetRef] = Field(default_factory=list, description="角色引用")
    scene: ShotPromptAssetRef | None = Field(None, description="场景引用")
    props: list[ShotPromptAssetRef] = Field(default_factory=list, description="道具引用")
    costumes: list[ShotPromptAssetRef] = Field(default_factory=list, description="服装引用")
    camera: ShotPromptCameraInfo = Field(default_factory=ShotPromptCameraInfo, description="镜头语言")
    atmosphere: str = Field("", description="氛围描述")
    visual_style: str = Field("", description="项目视觉风格")
    style: str = Field("", description="项目题材/风格")
    negative_prompt: str = Field("", description="默认负面提示词")


class VideoReferenceBindingRead(BaseModel):
    """视频生成中单张参考图的明确职责。"""

    file_id: str = Field(..., description="参考图文件 ID")
    frame_type: str = Field(..., description="帧类型：first/last/key")
    role: str = Field(..., description="参考图职责代码：start/end/key_state")
    title: str = Field(..., description="职责名称")
    instruction: str = Field(..., description="模型应如何使用该参考图")


class VideoTimelineSegmentRead(BaseModel):
    """覆盖完整视频时长的单个执行片段。"""

    start_s: float = Field(..., description="片段起始秒")
    end_s: float = Field(..., description="片段结束秒")
    purpose: str = Field(..., description="该片段的叙事作用")
    action: str = Field(..., description="主体动作与状态变化")
    camera: str = Field(..., description="构图与运镜")
    audio: str = Field(..., description="该时间段的对白或声音")


class VideoExecutionPlanRead(BaseModel):
    """视频模型执行前可审阅的时间轴与连续性计划。"""

    shot_id: str = Field(..., description="镜头 ID")
    target_duration_s: int = Field(..., description="目标时长（秒）")
    reference_mode: str = Field(..., description="参考图模式")
    generation_path: str = Field(..., description="生成路径代码")
    generation_path_label: str = Field(..., description="生成路径名称")
    start_state: str = Field(..., description="0 秒画面与动作状态")
    end_state: str = Field(..., description="结束时画面与动作状态")
    audio_approach: str = Field(..., description="全片声音策略")
    references: list[VideoReferenceBindingRead] = Field(default_factory=list, description="参考图及其职责")
    timeline: list[VideoTimelineSegmentRead] = Field(default_factory=list, description="完整时间轴")
    warnings: list[str] = Field(default_factory=list, description="生成前需注意的非阻塞提示")


class ShotVideoPromptPreviewRead(BaseModel):
    """视频提示词预览结果。"""

    shot_id: str = Field(..., description="镜头 ID")
    template_id: str | None = Field(None, description="使用的提示词模板 ID")
    template_name: str | None = Field(None, description="使用的提示词模板名称")
    rendered_prompt: str = Field(..., description="渲染后的提示词")
    pack: ShotVideoPromptPackRead = Field(..., description="渲染上下文包")
    execution_plan: VideoExecutionPlanRead = Field(..., description="视频执行计划")
    warnings: list[str] = Field(default_factory=list, description="渲染时发现的非阻塞提示")


class ShotVideoReadinessCheck(BaseModel):
    """单项视频生成准备度检查结果。"""

    key: str = Field(..., description="检查项 key")
    ok: bool = Field(..., description="是否通过")
    message: str = Field(..., description="面向前端展示的说明")


class ShotVideoReadinessRead(BaseModel):
    """镜头视频生成准备度。"""

    shot_id: str = Field(..., description="镜头 ID")
    reference_mode: str = Field(..., description="参考模式")
    ready: bool = Field(..., description="是否满足当前 reference_mode 下的视频生成条件")
    checks: list[ShotVideoReadinessCheck] = Field(default_factory=list, description="准备度检查项")


class ShotRuntimeSummaryRead(BaseModel):
    shot_id: str = Field(..., description="镜头 ID")
    has_active_tasks: bool = Field(..., description="是否存在进行中的关联任务")
    has_active_video_tasks: bool = Field(..., description="是否存在进行中的视频任务")
    has_active_prompt_tasks: bool = Field(..., description="是否存在进行中的提示词任务")
    has_active_frame_tasks: bool = Field(..., description="是否存在进行中的分镜帧图片任务")
    active_task_count: int = Field(..., description="进行中的唯一任务数")
