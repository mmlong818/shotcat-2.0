from __future__ import annotations

import sys
from pathlib import Path

BRIDGE_DIR = Path(__file__).resolve().parent
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

import extract_setup
from extract_setup import _identity_names, _merge_entity_entries, _ordered_variants


def test_merge_entity_entries_combines_alias_identity_before_variants() -> None:
    entries = [
        {
            "name": "周诚",
            "aliases": ["小周"],
            "base_appearance": "同一张脸",
            "looks": [
                {
                    "state_key": "adult_return",
                    "label": "成年返乡",
                    "description": "四十岁便装",
                    "is_base": True,
                }
            ],
        },
        {
            "name": "小周",
            "looks": [
                {
                    "state_key": "youth_student",
                    "label": "青年学生",
                    "description": "二十岁校服",
                    "is_base": True,
                }
            ],
        },
    ]

    merged = _merge_entity_entries(entries, fallback_label="剧本当前造型")

    assert len(merged) == 1
    assert set(_identity_names(merged[0])) == {"周诚", "小周"}
    assert [item["state_key"] for item in merged[0]["looks"]] == ["adult_return", "youth_student"]
    assert sum(item["is_base"] is True for item in merged[0]["looks"]) == 1


def test_ordered_variants_deduplicates_stable_state_key() -> None:
    entry = {
        "states": [
            {"state_key": "open", "label": "打开露出圆珠笔", "is_base": True},
            {"state_key": "open", "label": "打开状态", "is_base": False},
            {"state_key": "closed", "label": "闭合锈蚀", "is_base": False},
        ]
    }

    variants = _ordered_variants(entry, "基础状态")

    assert [item["state_key"] for item in variants] == ["open", "closed"]
    assert sum(item["is_base"] is True for item in variants) == 1


def test_run_overwrites_family_when_labels_change_instead_of_adding_duplicates(monkeypatch) -> None:
    """验证重复抽取按基础实体和 state_key 覆盖同步，不依赖状态显示名称。"""
    records: dict[str, dict[str, dict]] = {"character": {}, "scene": {}, "prop": {}}
    model_results = [
        {
            "characters": [],
            "scenes": [],
            "props": [
                {
                    "name": "金属铁盒",
                    "aliases": ["生锈的金属铁盒"],
                    "base_description": "旧铁盒",
                    "states": [
                        {"state_key": "closed", "label": "闭合锈蚀", "is_base": True},
                        {"state_key": "open", "label": "打开露出圆珠笔", "is_base": False},
                    ],
                }
            ],
        },
        {
            "characters": [],
            "scenes": [],
            "props": [
                {
                    "name": "金属铁盒",
                    "aliases": ["生锈的金属铁盒"],
                    "base_description": "同一只旧铁盒",
                    "states": [
                        {"state_key": "closed", "label": "锈蚀闭合", "is_base": True},
                        {"state_key": "open", "label": "开启含旧笔", "is_base": False},
                    ],
                }
            ],
        },
    ]

    def fake_chat_json(*_args, **_kwargs):
        """按调用顺序返回两次语义相同但措辞不同的模型结果。"""
        return model_results.pop(0)

    def fake_items(path: str) -> list[dict]:
        """模拟章节和三类实体列表接口。"""
        if path.startswith("/studio/chapters"):
            return [{"index": 1, "raw_text": "完整剧本"}]
        entity_type = path.split("/studio/entities/", 1)[1].split("?", 1)[0]
        return list(records[entity_type].values())

    def fake_request(method: str, path: str, body=None, _timeout=40):
        """模拟抽取脚本使用的项目与实体 CRUD。"""
        if method == "GET" and path.startswith("/studio/projects/"):
            return 200, {"data": {"style": "真人都市", "visual_style": "现实"}}
        entity_type = path.split("/studio/entities/", 1)[1].split("/", 1)[0]
        if method == "POST":
            records[entity_type][body["id"]] = dict(body)
            return 201, {"data": body}
        entity_id = path.rsplit("/", 1)[-1]
        if method == "PATCH":
            records[entity_type][entity_id].update(body)
            return 200, {"data": records[entity_type][entity_id]}
        if method == "DELETE":
            records[entity_type].pop(entity_id, None)
            return 200, {"data": None}
        raise AssertionError((method, path))

    monkeypatch.setattr(extract_setup, "chat_json", fake_chat_json)
    monkeypatch.setattr(extract_setup, "items", fake_items)
    monkeypatch.setattr(extract_setup, "_req", fake_request)

    extract_setup.run("project-1", "test-model")
    first_ids = set(records["prop"])
    extract_setup.run("project-1", "test-model")

    assert set(records["prop"]) == first_ids
    assert len(records["prop"]) == 2
    assert {item["name"] for item in records["prop"].values()} == {
        "金属铁盒 · 锈蚀闭合",
        "金属铁盒 · 开启含旧笔",
    }
