"""
Local markdown history retriever.

Reads the project-local memory written by `LocalMemoryWriter`:

  lifetrace/data/local_memory/{user_key}/{YYYY-MM-DD}/final_text.md

and retrieves relevant history blocks for the current query.

Design goals
- Minimal dependencies (no external search tools).
- Best-effort: failures must not break chat.
- Retrieval workflow:
  - Stage 1: scan today + yesterday only
  - If no hits: scan all earlier dates (all history)
  - Keyword extraction: prefer LLM if available, otherwise heuristic
  - Scoring: IDF-based + recency boost + role=user boost
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from lifetrace.llm.llm_client import LLMClient
from lifetrace.util.logging_config import get_logger
from lifetrace.util.path_utils import get_user_data_dir

logger = get_logger()

_KW_CLEAN_RE = re.compile(r"[\s\r\n\t，。！？、；：,.!?;:\(\)（）\[\]【】<>《》\"'“”‘’]+")


def _normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s


def _clean_kw(s: str) -> str:
    return _KW_CLEAN_RE.sub(" ", (s or "").strip().lower()).strip()


def _safe_user_key(user_key: str | None) -> str:
    key = (user_key or "").strip() or os.getenv("LIFETRACE_USER_KEY") or "default"
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        key = key.replace(ch, "_")
    key = key.replace("..", "_")
    return (key[:80] or "default").strip() or "default"


@dataclass(frozen=True)
class HistoryBlock:
    file_path: str
    file_date: str  # YYYY-MM-DD
    ts: datetime | None
    role: str
    content: str
    header_line: str


@dataclass(frozen=True)
class ScoredBlock:
    block: HistoryBlock
    matched_keywords: list[str]
    score: float


class LocalMdHistoryRetriever:
    def __init__(
        self,
        *,
        dir_name: str = "local_memory",
        top_k: int = 8,
        max_chars: int = 8000,
    ) -> None:
        self.dir_name = dir_name
        self.top_k = top_k
        self.max_chars = max_chars
        self.llm_client = LLMClient()

    def retrieve(self, *, user_query: str, user_key: str | None = None) -> dict[str, Any]:
        """Return {"context": str, "keywords": [...], "matched": int, "scanned_files": int, "mode": str}."""
        query = (user_query or "").strip()
        if not query:
            return {"context": "", "keywords": [], "matched": 0, "scanned_files": 0, "mode": "skip_empty"}

        user_key_safe = _safe_user_key(user_key)
        root = get_user_data_dir() / self.dir_name / user_key_safe
        if not root.exists():
            return {"context": "", "keywords": [], "matched": 0, "scanned_files": 0, "mode": "no_root"}

        keywords = self._extract_keywords(query)
        keywords = [kw for kw in keywords if kw]
        if not keywords:
            return {"context": "", "keywords": [], "matched": 0, "scanned_files": 0, "mode": "no_keywords"}

        today = date.today()
        stage1_dates = [today.strftime("%Y-%m-%d"), (today - timedelta(days=1)).strftime("%Y-%m-%d")]

        stage1_files = self._collect_md_files(root, include_dates=stage1_dates)
        stage1 = self._search_and_rank(stage1_files, keywords)
        if stage1:
            context = self._format_context(stage1[: self.top_k], keywords)
            return {
                "context": context,
                "keywords": keywords,
                "matched": len(stage1),
                "scanned_files": len(stage1_files),
                "mode": "today_yesterday",
            }

        # Stage 2: scan all (including earlier dates).
        all_files = self._collect_md_files(root, include_dates=None)
        stage2 = self._search_and_rank(all_files, keywords)
        context = self._format_context(stage2[: self.top_k], keywords) if stage2 else ""
        return {
            "context": context,
            "keywords": keywords,
            "matched": len(stage2),
            "scanned_files": len(all_files),
            "mode": "all_history",
        }

    def _collect_md_files(self, root: Path, include_dates: list[str] | None) -> list[Path]:
        files: list[Path] = []
        try:
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                if include_dates is not None and child.name not in include_dates:
                    continue
                md = child / "final_text.md"
                if md.exists() and md.is_file():
                    files.append(md)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Local history collect failed: %s", exc)
            return []

        # newest first
        files.sort(key=lambda p: p.parent.name, reverse=True)
        return files

    def _extract_keywords(self, user_query: str) -> list[str]:
        """Prefer LLM keyword extraction when available; otherwise simple heuristic."""
        q = (user_query or "").strip()
        if not q:
            return []

        # LLM extraction
        try:
            if self.llm_client and self.llm_client.is_available() and getattr(self.llm_client, "client", None):
                prompt = (
                    "从用户问题中提取用于检索的关键词（2-8个）。\n"
                    "要求：优先名词/动词/专有名词；不要输出停用词；用 JSON 数组输出。\n"
                    f"用户问题：{q}"
                )
                res = self.llm_client.client.chat.completions.create(
                    model=self.llm_client.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=120,
                )
                text = (res.choices[0].message.content or "").strip()
                # tolerate markdown code fences
                text = text.strip("`").strip()
                import json

                arr = json.loads(text)
                if isinstance(arr, list):
                    out = []
                    for item in arr:
                        s = str(item).strip()
                        s_clean = _clean_kw(s)
                        if s_clean and len(s_clean) >= 2:  # noqa: PLR2004
                            out.append(s_clean)
                    return out[:8]
        except Exception:
            pass

        # Heuristic fallback: keep 2-grams+ from cleaned tokens.
        cleaned = _clean_kw(q)
        parts = [p for p in cleaned.split(" ") if p and len(p) >= 2]  # noqa: PLR2004
        # de-dup keep order
        seen = set()
        out2 = []
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out2.append(p)
            if len(out2) >= 8:  # noqa: PLR2004
                break
        return out2

    def _search_and_rank(self, md_files: list[Path], keywords: list[str]) -> list[ScoredBlock]:
        if not md_files:
            return []

        kw_list = keywords
        kw_lowers = [str(kw).lower() for kw in kw_list]

        # IDF accumulation (average across files, like the reference workflow).
        idf_sum_by_kw: dict[str, float] = {kw: 0.0 for kw in kw_list}

        blocks_by_file: dict[str, list[HistoryBlock]] = {}
        file_lines_cache: dict[str, list[str]] = {}

        for md in md_files:
            try:
                raw = md.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            text = _normalize_text(raw)
            lines = text.split("\n")
            file_lines_cache[str(md)] = lines

            # doc_freq: count of lines that contain keyword (per file)
            doc_freq_counter: dict[str, int] = {kw: 0 for kw in kw_list}
            total_lines = len(lines) or 1
            for line in lines:
                line_lower = (line or "").lower()
                line_norm = _KW_CLEAN_RE.sub(" ", line_lower).strip()
                for kw, kw_lower in zip(kw_list, kw_lowers):
                    kw_clean = (kw_lower or "").strip()
                    if not kw_clean:
                        continue
                    if kw_clean in line_lower or kw_clean in line_norm:
                        doc_freq_counter[kw] += 1

            for kw in kw_list:
                df = doc_freq_counter.get(kw, 0)
                if df > 0:
                    idf_sum_by_kw[kw] += math.log(total_lines / df) + 1

            blocks_by_file[str(md)] = self._parse_blocks(md, text)

        denom = max(len(md_files), 1)
        idf_weights = {kw: round(idf_sum_by_kw.get(kw, 0.0) / denom, 2) for kw in kw_list}

        scored: list[ScoredBlock] = []
        for md in md_files:
            file_path = str(md)
            blocks = blocks_by_file.get(file_path) or []
            for block in blocks:
                matched = self._match_block_keywords(block, kw_list)
                if not matched:
                    continue
                score = sum(idf_weights.get(kw, 1.0) for kw in matched)

                # role=user boost
                if (block.role or "").strip().lower() == "user":
                    score += 0.6

                # recency boost (newer => higher). Use block timestamp when possible; otherwise date folder.
                age_days = self._estimate_age_days(block)
                score += 1.0 / (1.0 + max(age_days, 0))

                scored.append(ScoredBlock(block=block, matched_keywords=matched, score=score))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored

    def _parse_blocks(self, md_path: Path, text: str) -> list[HistoryBlock]:
        lines = text.split("\n")
        blocks: list[HistoryBlock] = []
        cur_header: str | None = None
        cur_role: str | None = None
        cur_ts: datetime | None = None
        buf: list[str] = []

        header_re = re.compile(r"^###\s+\[(?P<ts>[^\]]+)\]\s+(?P<role>\w+)\s*$")

        def flush():
            nonlocal cur_header, cur_role, cur_ts, buf
            if not cur_header or not cur_role:
                buf = []
                return
            content = "\n".join(buf).strip()
            if content:
                blocks.append(
                    HistoryBlock(
                        file_path=str(md_path),
                        file_date=md_path.parent.name,
                        ts=cur_ts,
                        role=cur_role,
                        content=content,
                        header_line=cur_header,
                    )
                )
            buf = []

        for line in lines:
            m = header_re.match(line.strip())
            if m:
                flush()
                cur_header = line.strip()
                cur_role = (m.group("role") or "").strip()
                ts_raw = (m.group("ts") or "").strip()
                cur_ts = None
                try:
                    # matches "YYYY-MM-DD HH:MM:SS"
                    cur_ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
                except Exception:
                    cur_ts = None
                continue
            if line.strip() == "---":
                flush()
                cur_header = None
                cur_role = None
                cur_ts = None
                continue
            if cur_header:
                # skip the meta line starting with ">"
                if line.strip().startswith("> "):
                    continue
                buf.append(line)

        flush()
        return blocks

    def _match_block_keywords(self, block: HistoryBlock, keywords: list[str]) -> list[str]:
        content = _normalize_text(block.content)
        content_lower = content.lower()
        content_norm = _KW_CLEAN_RE.sub(" ", content_lower).strip()
        matched: list[str] = []
        for kw in keywords:
            kw_clean = _clean_kw(kw)
            if not kw_clean:
                continue
            if kw_clean in content_lower or kw_clean in content_norm:
                matched.append(kw)
        # de-dup keep order
        seen = set()
        out = []
        for kw in matched:
            if kw in seen:
                continue
            seen.add(kw)
            out.append(kw)
        return out

    def _estimate_age_days(self, block: HistoryBlock) -> int:
        now = datetime.now()  # noqa: DTZ005
        if block.ts:
            dt = block.ts
        else:
            try:
                dt = datetime.strptime(block.file_date, "%Y-%m-%d")  # noqa: DTZ007
            except Exception:
                return 3650
        return max(0, (now.date() - dt.date()).days)

    def _format_context(self, scored_blocks: list[ScoredBlock], keywords: list[str]) -> str:
        if not scored_blocks:
            return ""

        parts: list[str] = []
        parts.append("【本地记忆检索上下文（来自 final_text.md；用于补全用户历史，不是新问题）】")
        parts.append(f"- keywords: {keywords}")
        parts.append("")

        total = 0
        for idx, item in enumerate(scored_blocks, 1):
            b = item.block
            ts_label = b.ts.strftime("%Y-%m-%d %H:%M:%S") if b.ts else b.file_date
            header = f"=== 记忆片段 {idx} ==="
            meta = f"出处: {b.file_date}/final_text.md | {ts_label} | role={b.role} | score={item.score:.2f} | matched={item.matched_keywords}"
            content = b.content.strip()

            chunk = "\n".join([header, meta, "", content, ""])
            if total + len(chunk) > self.max_chars:
                break
            parts.append(chunk)
            total += len(chunk)

        return "\n".join(parts).strip() + "\n"


