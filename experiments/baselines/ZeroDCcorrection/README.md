# ZeroDCcorrection

LLM-based error correction baseline (paper code under `ZeroDCcorrection/` and zero-shot variant under `ZeroDCcorrection-0-Shot/`).

## Run

```bash
cd ZeroDCcorrection
# set API keys / model names in correction.py (or your env)
python run_batch_experiments.py --dry-run
python run_batch_experiments.py
python run_experiments.py --evaluate-only
```

Point dataset and output directories at this repo’s `datasets/` and a local `results/` folder (do not hard-code machine-specific absolute paths).

See also `ZeroDCcorrection/README.md` (upstream) and `ZeroDCcorrection/EXPERIMENTS_README.md` for batch options.
