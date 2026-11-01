# ZeroDCcorrection batch experiments

Scripts for running and evaluating ZeroDCcorrection across multiple tables.

## Harness (Clean-Me-If-You-Can)

Use `experiments/harness/run_zerodccorrection.py` with `config_other_domains.json` (system `zerodccorrection`, **disabled by default**). The harness writes oracle detection via `evaluate.normalize`, calls `correction.py`, and scores `corrections.csv`. Do not enable until you intend to spend Gemini API budget.

**Gemini Batch API:** Not wired. Unlike Glocks (independent per-row prompts), ZeroDCcorrection’s LangChain pipeline is multi-stage (AutoCoT → code/FD gen → retrieval → threaded cell repairs). Batch needs a closed request set up front; a Glocks-style flag is not a drop-in. The final repair wave is the main cost and could be batch-submitted after retrieval with a moderate rewrite (bypass LangChain for that wave only); setup stages stay online.

## Audit artifacts (per run)

Written under the ZeroDCcorrection `--output_path` (and copied to the harness run dir):

| File | Contents |
|------|----------|
| `llm_calls.jsonl` | One JSON object per LLM call: stage, prompt, response, tokens (est + API if present), success/attempts |
| `repair_events.jsonl` | Cell-level provenance: `human` / `code` / `fd` / `llm` before→after |
| `token_usage.json` | Running totals (flushed after every call — safe if the process dies) |
| `human_repair_list.json` | Indices of oracle-labeled rows |
| `corrections.csv` | Full repaired table |
| `codes.txt` / `fds.txt` / `specific_examples.txt` | Intermediate ZeroDCcorrection artifacts |

## Scripts

| Script | Role |
|--------|------|
| `run_experiments.py` | Evaluate existing results or plan runs (`--evaluate-only`) |
| `run_batch_experiments.py` | Batch runner over a lake (`--dry-run` to preview) |
| `correction.py` | Core ZeroDCcorrection correction (set model / API keys here) |

## Configuration

Edit paths in `run_batch_experiments.py` / `run_experiments.py` to point at this repository, for example:

- Datasets: `../../../datasets/unrelated_tables/Quintet/`
- Results: a local `results/zerodccorrection/` directory under the repo root

Human-repair budgets typically: `[1, 2, 3, 5, 8, 10]`.

## Outputs

Per run (under your results root): `corrections.csv`, `output.txt`, `time_cost.txt`, and related logs. Aggregated CSVs are written by the batch/eval scripts.
