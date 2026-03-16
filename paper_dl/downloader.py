"""Core download logic for paper-dl."""

from __future__ import annotations

import json
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
        return f"{name}.pdf"


@dataclass
class DownloadResult:
    paper: Paper
    status: str          # "ok" | "skipped" | "failed"
    reason: str = ""


def load_papers(json_path: Path) -> list[Paper]:
    """Parse a pasa-format JSON file into Paper objects."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    papers = []
    for entry in data:
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

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(paper.pdf_url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read()

            if not content.startswith(b"%PDF"):
                if attempt < retries:
                    time.sleep(3 * attempt)
                    continue
                return DownloadResult(
                    paper=paper, status="failed", reason="response is not a valid PDF"
                )

            dest.write_bytes(content)
            return DownloadResult(paper=paper, status="ok")

        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return DownloadResult(
                    paper=paper, status="failed", reason=f"HTTP {e.code}"
                )
            if attempt < retries:
                time.sleep(5 * attempt)

        except Exception as e:  # noqa: BLE001
            if attempt < retries:
                time.sleep(5 * attempt)
            else:
                return DownloadResult(paper=paper, status="failed", reason=str(e))

    return DownloadResult(paper=paper, status="failed", reason="max retries exceeded")


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
                result: DownloadResult = future.result()
                if result.status == "ok":
                    ok.append(result)
                    bar.set_postfix_str(f"OK: {len(ok)}", refresh=False)
                elif result.status == "skipped":
                    skipped.append(result)
                    bar.set_postfix_str(f"skip: {len(skipped)}", refresh=False)
                else:
                    failed.append(result)
                    bar.set_postfix_str(f"fail: {len(failed)}", refresh=False)
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
