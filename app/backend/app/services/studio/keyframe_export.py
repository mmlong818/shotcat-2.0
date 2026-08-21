"""项目关键帧 ZIP 导出服务。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import AsyncIterator
import zlib

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.models.studio import Chapter, FileItem, Project, Shot, ShotFrameImage
from app.models.types import ShotFrameType
from app.services.common import entity_not_found


@dataclass(frozen=True)
class ArchiveItem:
    """单个待写入 ZIP 的存储文件。"""

    filename: str
    storage_key: str


def _safe_filename_part(value: str, fallback: str) -> str:
    """将镜头标题转换为跨平台可用的 ZIP 文件名片段。"""
    cleaned = "".join("_" if char in '\\/:*?\"<>|' else char for char in (value or "").strip())
    cleaned = " ".join(cleaned.split()).strip(". ")
    return cleaned[:100] or fallback


async def list_project_keyframe_export_items(
    db: AsyncSession,
    *,
    project_id: str,
) -> tuple[str, list[ArchiveItem]]:
    """读取项目关键帧清单，按章节和镜头顺序生成导出文件名。"""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Project"))

    rows = (
        await db.execute(
            select(
                Chapter.index,
                Shot.index,
                Shot.title,
                FileItem.storage_key,
            )
            .join(Shot, Shot.chapter_id == Chapter.id)
            .join(ShotFrameImage, ShotFrameImage.shot_detail_id == Shot.id)
            .join(FileItem, FileItem.id == ShotFrameImage.file_id)
            .where(
                Chapter.project_id == project_id,
                ShotFrameImage.frame_type == ShotFrameType.key,
                ShotFrameImage.file_id.is_not(None),
            )
            .order_by(Chapter.index.asc(), Shot.index.asc())
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="当前项目没有可导出的关键帧")

    items = []
    for chapter_index, shot_index, title, storage_key in rows:
        extension = Path(str(storage_key)).suffix.lower() or ".png"
        filename = (
            f"第{int(chapter_index):02d}集_第{int(shot_index):03d}镜_"
            f"{_safe_filename_part(str(title), f'镜头{int(shot_index):03d}')}{extension}"
        )
        items.append(ArchiveItem(filename=filename, storage_key=str(storage_key)))
    archive_name = f"{_safe_filename_part(project.name, '项目')}_关键帧.zip"
    return archive_name, items


def _zip_entry(filename: str, content: bytes, offset: int) -> tuple[bytes, bytes, bytes, bytes, int]:
    """构建一个无压缩 ZIP 条目，返回局部头、名称、内容、中央目录记录和下一个偏移量。"""
    encoded_name = filename.encode("utf-8")
    crc = zlib.crc32(content) & 0xFFFFFFFF
    size = len(content)
    flags = 0x0800  # UTF-8 文件名
    local_header = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        20,
        flags,
        0,
        0,
        0,
        crc,
        size,
        size,
        len(encoded_name),
        0,
    )
    central_header = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50,
        20,
        20,
        flags,
        0,
        0,
        0,
        crc,
        size,
        size,
        len(encoded_name),
        0,
        0,
        0,
        0,
        0,
        offset,
    ) + encoded_name
    next_offset = offset + len(local_header) + len(encoded_name) + size
    return local_header, encoded_name, content, central_header, next_offset


async def iter_file_archive(items: list[ArchiveItem], *, skipped_label: str) -> AsyncIterator[bytes]:
    """边读取单个文件边输出 ZIP，避免大项目在服务器内存或临时盘堆积整包文件。"""
    central_records: list[bytes] = []
    skipped: list[str] = []
    offset = 0
    for item in items:
        try:
            content = await storage.download_file(key=item.storage_key)
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{item.filename}：{type(exc).__name__}: {exc}")
            continue
        local_header, encoded_name, data, central, offset = _zip_entry(item.filename, content, offset)
        central_records.append(central)
        yield local_header
        yield encoded_name
        yield data

    if skipped:
        note = (f"以下{skipped_label}无法读取，未包含在本次导出中：\n" + "\n".join(skipped) + "\n").encode("utf-8")
        local_header, encoded_name, data, central, offset = _zip_entry(f"未导出{skipped_label}.txt", note, offset)
        central_records.append(central)
        yield local_header
        yield encoded_name
        yield data

    central_directory = b"".join(central_records)
    yield central_directory
    yield struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        len(central_records),
        len(central_records),
        len(central_directory),
        offset,
        0,
    )


async def iter_keyframe_archive(items: list[ArchiveItem]) -> AsyncIterator[bytes]:
    """导出关键帧兼容入口。"""
    async for chunk in iter_file_archive(items, skipped_label="关键帧"):
        yield chunk
