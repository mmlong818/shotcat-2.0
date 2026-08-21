"""从完整剧本提取项目级事实、规则与连续性候选。"""

from __future__ import annotations

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase
from app.schemas.studio.project_brain import ProjectBrainExtractionResult


_SYSTEM_PROMPT = """\
你是 Shotcat 2.0 的项目大脑分析员。请先通读全部剧本，再建立去重后的项目级事实与规则候选。

分析顺序必须是：
1. 全文识别事实类别；
2. 合并同义项与重复项；
3. 区分原文明示事实和必要派生约束；
4. 最后检查跨章节、跨场景、跨镜头的连续性。

可用 category：
- fact：原文明示的时间、事件、因果或世界事实；
- character：角色身份、关系、稳定外观、行为边界；
- environment：空间结构、地点关系、时间天气和环境变化；
- prop：真正影响剧情或画面的关键道具；
- style：原文明确要求的视觉、时代或媒介风格；
- narrative：主冲突、关键信息揭示、情绪或叙事目标；
- continuity：跨段落必须持续成立的状态、方向、伤势、持物或空间关系。

强约束：
- 不得把常识、猜测或创作建议伪装为原文事实；无法确认就不要输出。
- 不得按场景常识新增手机、背包、雨伞、杯子等普通物件。
- 同一事实只输出一次；角色别名应合并，但证据中的原文称呼保留。
- 每条必须短而明确，能直接约束后续设定、拆镜头或生图。
- evidence 只放支持该条目的原文短句，格式为 {"quote": "原文", "source_ref": "章节位置"}。
- source_ref 尽量写清章节；无法精确定位时留空，不得编造行号。
- 派生约束只能是原文事实的直接后果，并在 content 中明确写“由原文事实派生”。
- 不输出状态、锁定、版本或数据库 ID；系统会把所有结果保存为 AI 待确认候选。
- 只输出符合 ProjectBrainExtractionResult 的 JSON。
"""

_PROMPT = PromptTemplate(
    input_variables=["project_name", "script_text"],
    template="## 项目名称\n{project_name}\n\n## 完整剧本\n{script_text}\n\n## 输出 JSON\n",
)


class ProjectBrainExtractorAgent(AgentBase[ProjectBrainExtractionResult]):
    @property
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return _PROMPT

    @property
    def output_model(self) -> type[ProjectBrainExtractionResult]:
        return ProjectBrainExtractionResult
