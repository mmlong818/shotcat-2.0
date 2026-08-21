"""共享 HTTP 工具：跟随后端分页信封逐页拉全量 items。仅标准库。"""
from __future__ import annotations
import json, urllib.error, urllib.parse, urllib.request


def _get(url, timeout=30):
    r = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def get_all(base, path, params=None, *, page_size=100, timeout=30):
    """按分页信封 {data:{items, pagination:{page, page_size, total, max_page}}} 逐页取全量 items。
    base 形如 http://localhost:8000/api/v1；path 可自带 query（会与 params 合并）。
    page_size 后端上限 100，超过会被后端夹回。某页请求失败即停止（返回已收集部分）。"""
    parsed = urllib.parse.urlsplit(path)
    q = dict(urllib.parse.parse_qsl(parsed.query))
    if params:
        q.update({k: str(v) for k, v in params.items()})
    q["page_size"] = str(q.get("page_size", page_size))
    out = []
    page = 1
    while True:
        q["page"] = str(page)
        url = base + parsed.path + "?" + urllib.parse.urlencode(q)
        code, j = _get(url, timeout)
        if code >= 400:
            break
        data = j.get("data") or {}
        out += data.get("items", [])
        pg = data.get("pagination") or {}
        max_page = pg.get("max_page")
        if not max_page or page >= max_page:
            break
        page += 1
    return out
