🌐 [English](README.md) | [简体中文](README.zh-CN.md)

---

# paper-dl

**The missing last mile between PaSa and your local AI research workflow.**

---

## Background

[PaSa](https://github.com/bytedance/pasa) (ByteDance, ACL 2025) is an LLM-powered academic paper search agent. Given a research question, PaSa autonomously:

1. Generates search queries
2. Crawls arxiv and expands citation networks
3. Scores each paper for relevance using a fine-tuned selector model
4. Returns a ranked list of results — **exported as a JSON file**

**The problem:** PaSa's JSON only contains metadata — titles, abstracts, arxiv links, and relevance scores. It does not download the actual papers.

**paper-dl fills that gap.** It reads PaSa's JSON and batch-downloads every paper as a PDF, giving you a local library you can feed directly into an AI agent for deep literature analysis.

---

## Requirements

- Python 3.10 or higher
- One external dependency: [tqdm](https://github.com/tqdm/tqdm) (installed automatically)

---

## Installation

```bash
git clone https://github.com/ruizelyu/paper-dl.git
cd paper-dl
pip install -r requirements.txt
pip install .
```

Verify the installation:

```bash
paper-dl --version
# paper-dl 0.1.0
```

---

## Quick Start

### Step 1 — Search on PaSa

Go to [pasa-agent.ai](https://pasa-agent.ai) and type your research question in English.

![PaSa search interface](assets/step1-search.png)

> Example: *"defense methods for LLM agents against prompt injection attacks"*

### Step 2 — Export the JSON file

Once results appear, **① click the download icon** (top right of the results panel) to save the results as a `.json` file. Before downloading, you can **② check or uncheck** individual papers to include or exclude them.

![PaSa export JSON](assets/step2-export.png)

The downloaded file will look like this:

```json
[
  {
    "link": "https://www.arxiv.org/abs/2509.07764",
    "title": "AgentSentinel: An End-to-End and Real-Time Security Defense Framework",
    "publish_time": "20250909",
    "authors": ["Haitao Hu", "Peng Chen"],
    "abstract": "...",
    "score": 0.99
  },
  ...
]
```

Save it anywhere on your computer, for example:

```
~/Downloads/agent_defense.json
```

### Step 3 — Run paper-dl

Open a terminal and run:

```bash
paper-dl ~/Downloads/agent_defense.json
```

You will see a progress bar:

```
Output directory : /Users/you/Downloads/agent_defense
Total papers     : 53
Concurrency      : 3

100%|████████████████████| 53/53 [02:14<00:00,  OK: 51, fail: 2]

Failed list saved to: /Users/you/Downloads/agent_defense/failed.txt

Done.  Success: 51  Skipped: 0  Failed: 2
```

### Step 4 — Find your PDFs

paper-dl creates a folder with the **same name as your JSON file**, in the **same directory**:

```
~/Downloads/
├── agent_defense.json                  ← your PaSa export (unchanged)
└── agent_defense/                      ← created by paper-dl
    ├── AgentSentinel_ An End-to-End and Real-Time Security Defense Framework.pdf
    ├── A-MemGuard_ A Proactive Defense Framework for LLM-Based Agent Memory.pdf
    ├── Policy Smoothing for Provably Robust Reinforcement Learning.pdf
    ├── ...
    └── failed.txt                      ← only created if some papers failed
```

---

## Usage

```bash
# Download to a folder named after the JSON file (default)
paper-dl results.json

# Specify a custom output directory
paper-dl results.json -o ./my_papers

# Increase concurrency for faster downloads
paper-dl results.json -c 5

# All options together
paper-dl results.json -o ./papers -c 3 -r 3
```

**All options**

| Option | Default | Description |
|--------|---------|-------------|
| `json_file` | — | Path to the PaSa-exported JSON file |
| `-o, --output` | same directory as JSON, folder named after JSON | Output directory for PDFs |
| `-c, --concurrency` | `3` | Number of simultaneous downloads |
| `-r, --retries` | `3` | Max retry attempts per failed paper |
| `-v, --version` | — | Show version and exit |

---

## Re-running safely

If you run paper-dl again on the same JSON file, already-downloaded PDFs are automatically skipped. It is safe to re-run at any time:

```
Done.  Success: 0  Skipped: 51  Failed: 2
```

---

## Handling failures

If some papers could not be downloaded, a `failed.txt` file is created inside the output folder:

```
https://arxiv.org/abs/2508.02961	Defend LLMs Through Self-Consciousness	HTTP 404
https://arxiv.org/abs/2501.99999	Some Other Paper	max retries exceeded
```

Each line contains: `arxiv link`, `paper title`, and `reason for failure`, separated by tabs.

Common reasons:
- **HTTP 404** — the paper is not yet publicly available on arxiv
- **max retries exceeded** — a temporary network issue; try running again

---

## Notes

- Only supports **arxiv** papers. PaSa currently indexes arxiv, so all results are compatible.
- Default concurrency is **3** to avoid overloading arxiv's servers. Do not set it too high.

---

## License

MIT © paper-dl contributors
