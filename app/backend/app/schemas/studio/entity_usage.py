"""造型资产在镜头画面中的使用与派生状态回退结果。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EntityUsageShotRead(BaseModel):
    """一条资产被镜头画面引用的摘要，用于造型页展示。"""

    model_config = ConfigDict(extra="forbid")

    shot_id: str = Field(..., description="镜头 ID")
    chapter_id: str = Field(..., description="所属章节 ID")
    shot_index: int = Field(..., description="章节内镜头序号")
    title: str = Field(..., description="镜头标题")


class EntityUsageSummaryRead(BaseModel):
    """单个资产的镜头使用汇总，未使用时 shots 为空。"""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(..., description="资产 ID")
    shots: list[EntityUsageShotRead] = Field(default_factory=list, description="引用该资产的镜头")


class EntityDeleteResult(BaseModel):
    """删除资产后的引用回退结果。"""

    model_config = ConfigDict(extra="forbid")

    deleted_entity_id: str = Field(..., description="已删除的资产 ID")
    fallback_entity_id: str | None = Field(None, description="派生状态回退到的基准资产 ID")
    fallback_entity_name: str | None = Field(None, description="派生状态回退到的基准资产名称")
    reassigned_shot_count: int = Field(0, ge=0, description="已改为引用基准资产的镜头数量")
