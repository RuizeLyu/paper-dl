"""Core download logic for paper-dl."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tqdm import tqdm


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Matches arxiv IDs like 2301.12345 or 2301.12345v2
_ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})")
_INVALID_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


@dataclass
class Paper:
    title: str
    link: str
    arxiv_id: Optional[str] = field(default=None, init=False)

    def __post_init__(self) -> None:
        m = _ARXIV_ID_RE.search(self.link)
        self.arxiv_id = m.group(1) if m else None

    @property
    def pdf_url(self) -> Optional[str]:
        if self.arxiv_id:
            return f"https://arxiv.org/pdf/{self.arxiv_id}.pdf"
        return None

    @property
    def safe_filename(self) -> str:
        name = _INVALID_CHARS_RE.sub("_", self.title)
        name = re.sub(r"\s+", " ", name).strip()
        if len(name) > 100:
            name = name[:100].rstrip()
        # Fallback for empty names; append arxiv ID to avoid collisions
        name = name or "unknown"
        if self.arxiv_id:
            name = f"{name} [{self.arxiv_id}]"
        return f"{name}.pdf"


@dataclass
class DownloadResult:
    paper: Paper
    status: str          # "ok" | "skipped" | "failed"
    reason: str = ""


def load_papers(json_path: Path) -> list[Paper]:
    """Parse a pasa-format JSON file into Paper objects."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: invalid JSON in {json_path}: {exc}") from exc

    if not isinstance(data, list):
        raise SystemExit(f"Error: expected a JSON array, got {type(data).__name__}")

    papers = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if title and link:
            papers.append(Paper(title=title, link=link))
    return papers


def _download_one(paper: Paper, dest: Path, retries: int = 3) -> DownloadResult:
    """Download a single PDF. Returns a DownloadResult."""
    if dest.exists():
        return DownloadResult(paper=paper, status="skipped", reason="already exists")

    if not paper.pdf_url:
        return DownloadResult(
            paper=paper, status="failed", reason=f"cannot parse arxiv ID from: {paper.link}"
        )

    tmp_dest = dest.with_suffix(".pdf.tmp")
    last_error: str = "max retries exceeded"

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(paper.pdf_url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                first_chunk = resp.read(65536)
                if not first_chunk or not first_chunk.startswith(b"%PDF"):
                    last_error = "response is not a valid PDF"
                    if attempt < retries:
                        time.sleep(3 * attempt)
                        continue
                    return DownloadResult(
                        paper=paper, status="failed", reason=last_error
                    )

                with open(tmp_dest, "wb") as f:
                    f.write(first_chunk)
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)

            os.replace(tmp_dest, dest)
            return DownloadResult(paper=paper, status="ok")

        except urllib.error.HTTPError as e:
            tmp_dest.unlink(missing_ok=True)
            last_error = f"HTTP {e.code}"
            if e.code in (403, 404):
                return DownloadResult(
                    paper=paper, status="failed", reason=last_error
                )
            if attempt < retries:
                time.sleep(5 * attempt)

        except OSError as e:
            tmp_dest.unlink(missing_ok=True)
            last_error = f"write error: {e}"
            return DownloadResult(paper=paper, status="failed", reason=last_error)

        except Exception as e:  # noqa: BLE001
            tmp_dest.unlink(missing_ok=True)
            last_error = str(e)
            if attempt < retries:
                time.sleep(5 * attempt)

    return DownloadResult(paper=paper, status="failed", reason=last_error)


def download_papers(
    json_path: Path,
    output_dir: Optional[Path] = None,
    concurrency: int = 3,
    retries: int = 3,
) -> tuple[list[DownloadResult], list[DownloadResult], list[DownloadResult]]:
    """
    Download all papers from a pasa JSON file.

    Returns:
        (ok_results, skipped_results, failed_results)
    """
    papers = load_papers(json_path)
    if not papers:
        print("No papers found in the input file.")
        return [], [], []

    if output_dir is None:
        output_dir = json_path.parent / json_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output directory : {output_dir}")
    print(f"Total papers     : {len(papers)}")
    print(f"Concurrency      : {concurrency}\n")

    ok: list[DownloadResult] = []
    skipped: list[DownloadResult] = []
    failed: list[DownloadResult] = []

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_download_one, p, output_dir / p.safe_filename, retries): p
            for p in papers
        }

        with tqdm(total=len(papers), unit="paper", ncols=80) as bar:
            for future in as_completed(futures):
                try:
                    result: DownloadResult = future.result()
                except Exception as exc:
                    paper = futures[future]
                    result = DownloadResult(paper=paper, status="failed", reason=str(exc))

                if result.status == "ok":
                    ok.append(result)
                elif result.status == "skipped":
                    skipped.append(result)
                else:
                    failed.append(result)
                bar.set_postfix(OK=len(ok), skip=len(skipped), fail=len(failed), refresh=False)
                bar.update(1)

    # Write failed list
    if failed:
        failed_log = output_dir / "failed.txt"
        with open(failed_log, "w", encoding="utf-8") as f:
            for r in failed:
                f.write(f"{r.paper.link}\t{r.paper.title}\t{r.reason}\n")
        print(f"\nFailed list saved to: {failed_log}")

    print(f"\nDone.  Success: {len(ok)}  Skipped: {len(skipped)}  Failed: {len(failed)}")
    return ok, skipped, failed
