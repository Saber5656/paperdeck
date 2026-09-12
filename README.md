# paperdeck

[![CI](https://github.com/Saber5656/paperdeck/actions/workflows/ci.yml/badge.svg)](https://github.com/Saber5656/paperdeck/actions/workflows/ci.yml)

paperdeck turns scholarly PDFs, LaTeX projects, and arXiv papers into self-contained HTML reading decks. The result keeps section navigation, reference jumps, equation previews, a table of contents, keyboard controls, and a browser reader that works offline.

> **Demo media:** an animated demo GIF will be added after the v1 reader sweep.

## Install

```sh
uv tool install paperdeck
# or
pipx install paperdeck
```

The LaTeX engine uses Pandoc. Install it with the package manager for your system:

```sh
# macOS
brew install pandoc
# Debian/Ubuntu
sudo apt-get install pandoc
# Fedora
sudo dnf install pandoc
```

Set an LLM provider for the PDF engine. The engine sends extracted paper text and cropped equation images only when it needs structure, bibliography, citation, or equation transcription help.

```sh
export OPENAI_API_KEY="..."
```

An OpenAI-compatible local server needs no key. For Ollama, put this in `~/.config/paperdeck/config.toml`:

```toml
[llm]
base_url = "http://localhost:11434/v1"
model = "llama3.2"
vlm_model = "llava"
api_key_env = "OLLAMA_API_KEY"
cache = true
max_cost_usd = 0.0
```

## Quickstart

```sh
paperdeck convert 2401.12345 --output out.html
paperdeck convert paper.tex --output out.html
paperdeck convert paper.pdf --engine pdf --output out.html
```

Each command writes one self-contained HTML file. Use `paperdeck doctor --json` to check local prerequisites before converting.

## Reader features

| Feature | How to use |
| --- | --- |
| Section jumps | Click the table of contents or press `g` then `s` |
| Figure/table previews | Select the caption or use the linked reference |
| Equation previews | Hover an equation image; unverified PDF transcriptions stay marked |
| Table of contents | Press `t` to focus it |
| Themes | Press `d` to switch light/dark mode |
| Reading position | The reader restores the last position in local browser storage |
| Keyboard navigation | `j`/`k` move between sections, `/` focuses search, `?` shows keys |

## Engines

| Input | Engine and fidelity | Cost and offline behavior |
| --- | --- | --- |
| arXiv ID | arXiv HTML when available; LaTeX source fallback | Network fetch; `--offline` uses cache |
| `.tex` or source archive | LaTeX/Pandoc engine, highest semantic fidelity | Local and offline after dependencies are installed |
| `.pdf` | PDF text layout plus deterministic crops; best-effort semantic recovery | LLM usage may cost money; configure `max_cost_usd`; `--offline` requires cached LLM replies |

Select explicitly with `--engine latex`, `--engine pdf`, or `--engine arxiv-html` when the input supports more than one path. A declined estimate or an exhausted budget preserves image equations and records a warning rather than inventing LaTeX.

## Limitations

PDFs do not contain the full semantic structure of a source document. Column detection, reading order, bibliography parsing, and citation linking therefore use conservative heuristics and may produce `unhandled` blocks. Equation images are the source of truth; PDF-engine VLM LaTeX is an unverified transcription and is never treated as authoritative. Complex LaTeX packages, custom fonts, unusual macros, scanned PDFs, and malformed files can reduce fidelity. See [`docs/DESIGN.md`](docs/DESIGN.md) and [`docs/decisions/`](docs/decisions/) for the canonical design and tradeoffs.

## Privacy and security

Generated HTML contains vendored assets and makes zero external requests. The PDF engine sends paper text and cropped images to the configured LLM provider only when conversion requires it; local LaTeX and cached offline conversions do not send those requests. Read [`SECURITY.md`](SECURITY.md) before processing untrusted documents.

## 日本語

paperdeck は、論文 PDF・LaTeX・arXiv の文書を、参照ジャンプや数式プレビューを備えた自己完結型の HTML 読書デッキへ変換します。`uv tool install paperdeck` または `pipx install paperdeck` で導入し、LaTeX 入力には Pandoc を OS のパッケージマネージャーから追加してください。PDF エンジンだけは、構造判定・参考文献・引用・数式転記のために、設定した LLM へ本文や数式画像を送ることがあります。生成物はオフラインで動作し、未検証の数式転記は画像を正とします。詳しい仕様・制約は [`docs/DESIGN.md`](docs/DESIGN.md)、安全な利用方法は [`SECURITY.md`](SECURITY.md) を参照してください。
