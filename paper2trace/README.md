# paper2trace

Extract the implicit research process (hypothesis chains, abandoned approaches,
critical analyses) from an academic paper or technical report, and emit it as
structured SFT / DPO / ReAct artifacts.

Part of the [Papyrus](../README.md) suite.

## What it produces

For each input document, `paper2trace` writes a set of JSON / text files under
`paper2trace/output/<paper_id>/`:

| File | Content |
|------|---------|
| `..._1_structure.json` | Paper metadata, sections, figures, tables |
| `..._1b_raw_data.json` | Tables, quantitative claims, abandoned methods |
| `..._2_hypothesis_chain.json` | `hypothesis → experiment → result → decision` nodes |
| `..._3_critical_analysis.json` | Blind spots, fragile assumptions, untested directions |
| `..._4a_sft.json` | Research-reasoning Q&A pairs (instruction / output) |
| `..._4b_dpo.json` | Preference pairs (prompt / chosen / rejected) |
| `..._4c_react.txt` | Reconstructed ReAct trace of the research process |
| `..._5_quality_report.json` | Rule-based checks |
| `..._5b_semantic_quality.json` | LLM-based semantic checks |

See [`../examples/boyer_moore_trace/`](../examples/boyer_moore_trace/) for the
full output of one real run (Boyer & Moore 1977).

## Install

```bash
pip install python-docx pdfplumber anthropic openai
```

## Configure

Copy `.env.example` to `.env` and fill in the required keys:

```bash
cp .env.example .env
# edit .env
```

Shell environment variables override `.env`. You can also point to a different
env file with `--env-file`.

## Run

```bash
python paper2trace.py /path/to/paper.pdf
python paper2trace.py /path/to/report.docx
python paper2trace.py /path/to/report.txt

# custom paper id (default is the filename)
python paper2trace.py /path/to/paper.pdf --paper-id my_paper_001

# custom env file
python paper2trace.py /path/to/report.txt --env-file /path/to/custom.env
```

## Notes

- All outputs are LLM-generated extractions. The pipeline ships rule-based
  (`5_quality_report.json`) and semantic-LLM (`5b_semantic_quality.json`)
  quality checks; for downstream training-data use, especially `4a_sft.json`
  and `4b_dpo.json`, an additional curation pass is recommended.
- "Abandoned approaches" and "fragile assumptions" are *inferred* from
  textual cues in the paper itself — they reconstruct likely research
  decisions, not authors' private notes.
- Quality thresholds in `.env.example` (`QUALITY_MIN_*`) can be tightened
  or relaxed per-deployment depending on how strict downstream consumers are.
