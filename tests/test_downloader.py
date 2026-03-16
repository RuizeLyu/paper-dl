"""Unit tests for paper_dl.downloader (no network calls)."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile

from paper_dl.downloader import (
    DownloadResult,
    Paper,
    _download_one,
    load_papers,
)


# ---------------------------------------------------------------------------
# Paper dataclass
# ---------------------------------------------------------------------------

class TestPaperArxivId(unittest.TestCase):
    def test_abs_url(self):
        p = Paper(title="T", link="https://www.arxiv.org/abs/2509.07764")
        self.assertEqual(p.arxiv_id, "2509.07764")

    def test_pdf_url(self):
        p = Paper(title="T", link="https://arxiv.org/pdf/2305.17342")
        self.assertEqual(p.arxiv_id, "2305.17342")

    def test_five_digit_id(self):
        p = Paper(title="T", link="https://arxiv.org/abs/2301.12345")
        self.assertEqual(p.arxiv_id, "2301.12345")

    def test_non_arxiv_link(self):
        p = Paper(title="T", link="https://openreview.net/forum?id=abc")
        self.assertIsNone(p.arxiv_id)

    def test_empty_link(self):
        p = Paper(title="T", link="")
        self.assertIsNone(p.arxiv_id)

    def test_pdf_url_property(self):
        p = Paper(title="T", link="https://arxiv.org/abs/2509.07764")
        self.assertEqual(p.pdf_url, "https://arxiv.org/pdf/2509.07764.pdf")

    def test_pdf_url_none_when_no_id(self):
        p = Paper(title="T", link="https://example.com")
        self.assertIsNone(p.pdf_url)


class TestPaperSafeFilename(unittest.TestCase):
    def test_basic(self):
        p = Paper(title="My Paper", link="")
        self.assertEqual(p.safe_filename, "My Paper.pdf")

    def test_invalid_chars_replaced(self):
        p = Paper(title='Paper: A/B "Test"', link="")
        self.assertNotIn(":", p.safe_filename)
        self.assertNotIn("/", p.safe_filename)
        self.assertNotIn('"', p.safe_filename)
        self.assertTrue(p.safe_filename.endswith(".pdf"))

    def test_long_title_truncated(self):
        p = Paper(title="A" * 200, link="")
        # filename = title (<=100) + ".pdf"
        self.assertLessEqual(len(p.safe_filename), 105)

    def test_extra_whitespace_collapsed(self):
        p = Paper(title="A   B", link="")
        self.assertEqual(p.safe_filename, "A B.pdf")


# ---------------------------------------------------------------------------
# load_papers
# ---------------------------------------------------------------------------

class TestLoadPapers(unittest.TestCase):
    def _write_json(self, data, tmp_dir):
        path = Path(tmp_dir) / "papers.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_valid_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_json(
                [
                    {"title": "Paper A", "link": "https://arxiv.org/abs/2001.00001"},
                    {"title": "Paper B", "link": "https://arxiv.org/abs/2001.00002"},
                ],
                tmp,
            )
            papers = load_papers(path)
        self.assertEqual(len(papers), 2)
        self.assertEqual(papers[0].title, "Paper A")

    def test_skips_missing_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_json(
                [{"link": "https://arxiv.org/abs/2001.00001"}], tmp
            )
            papers = load_papers(path)
        self.assertEqual(papers, [])

    def test_skips_missing_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_json([{"title": "Paper A"}], tmp)
            papers = load_papers(path)
        self.assertEqual(papers, [])

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_json([], tmp)
            papers = load_papers(path)
        self.assertEqual(papers, [])

    def test_extra_fields_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_json(
                [
                    {
                        "title": "Paper A",
                        "link": "https://arxiv.org/abs/2001.00001",
                        "authors": ["Alice"],
                        "score": 0.99,
                    }
                ],
                tmp,
            )
            papers = load_papers(path)
        self.assertEqual(len(papers), 1)


# ---------------------------------------------------------------------------
# _download_one
# ---------------------------------------------------------------------------

class TestDownloadOne(unittest.TestCase):
    def _make_paper(self, arxiv_id="2001.00001"):
        return Paper(
            title="Test Paper",
            link=f"https://arxiv.org/abs/{arxiv_id}",
        )

    def test_skips_existing_file(self):
        paper = self._make_paper()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "test.pdf"
            dest.write_bytes(b"%PDF-fake")
            result = _download_one(paper, dest)
        self.assertEqual(result.status, "skipped")

    def test_fails_when_no_arxiv_id(self):
        paper = Paper(title="T", link="https://example.com/paper")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "test.pdf"
            result = _download_one(paper, dest)
        self.assertEqual(result.status, "failed")
        self.assertIn("cannot parse arxiv ID", result.reason)

    @patch("paper_dl.downloader.urllib.request.urlopen")
    def test_successful_download(self, mock_urlopen):
        fake_pdf = b"%PDF-1.4 fake content"
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_pdf
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        paper = self._make_paper()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "test.pdf"
            result = _download_one(paper, dest)
            self.assertEqual(result.status, "ok")
            self.assertEqual(dest.read_bytes(), fake_pdf)

    @patch("paper_dl.downloader.urllib.request.urlopen")
    def test_fails_on_404(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=404, msg="Not Found", hdrs=None, fp=None
        )
        paper = self._make_paper()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "test.pdf"
            result = _download_one(paper, dest, retries=1)
        self.assertEqual(result.status, "failed")
        self.assertIn("404", result.reason)

    @patch("paper_dl.downloader.urllib.request.urlopen")
    def test_fails_when_response_is_not_pdf(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>not a pdf</html>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        paper = self._make_paper()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "test.pdf"
            result = _download_one(paper, dest, retries=1)
        self.assertEqual(result.status, "failed")
        self.assertIn("not a valid PDF", result.reason)

    @patch("paper_dl.downloader.time.sleep")
    @patch("paper_dl.downloader.urllib.request.urlopen")
    def test_retries_on_server_error(self, mock_urlopen, mock_sleep):
        import urllib.error
        # First two attempts: 500 error. Third: success.
        fake_pdf = b"%PDF-ok"
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_pdf
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [
            urllib.error.HTTPError("", 500, "Server Error", None, None),
            urllib.error.HTTPError("", 500, "Server Error", None, None),
            mock_resp,
        ]

        paper = self._make_paper()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "test.pdf"
            result = _download_one(paper, dest, retries=3)
        self.assertEqual(result.status, "ok")
        self.assertEqual(mock_urlopen.call_count, 3)


if __name__ == "__main__":
    unittest.main()
