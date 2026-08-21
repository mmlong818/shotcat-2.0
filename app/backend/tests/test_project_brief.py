from __future__ import annotations

from app.api.v1.routes.studio.projects import _brief_brain_entries, _normalize_project_stats


def test_project_brief_is_normalized_and_seeds_locked_user_rules() -> None:
    stats, brief = _normalize_project_stats({
        "project_brief": {
            "format": "竖屏漫剧",
            "runtime_minutes": 3,
            "audience": "悬疑短剧观众",
            "tone": "克制、悬疑",
            "premise": "一把被烧掉的钥匙重新出现。",
        },
    })

    assert brief is not None
    assert stats["project_brief"]["runtime_minutes"] == 3
    entries = _brief_brain_entries("p1", brief)
    assert [entry.title for entry in entries] == ["制作规格", "情绪基调", "故事承诺"]
    assert all(entry.project_id == "p1" for entry in entries)
    assert all(entry.origin == "user" and entry.status == "confirmed" and entry.locked for entry in entries)
