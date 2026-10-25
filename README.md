# Automated-SPICE-Code-Generation
This is the repo of the project on an fully automated SPICE code generation framework with optimazition on performance-cost tradeoffs

Project additions: [local Pro baseline](baselines/analogcoder_pro/README.md),
[experiment log](EXPERIMENT_LOG.md), [usage accounting](docs/USAGE_ACCOUNTING.md),
and [implementation notes](IMPLEMENTATION_LOG.md).

---

# AnalogCoder: Analog Circuit Design via Training-Free Code Generation

**New:** Our paper is accepted by **AAAI 2025** as an **Oral Presentation (Top 5%)**, and selected as **AAAI 2025 Most Influential Papers**.

<p align="center">
  <img src="AnalogCoder_label.png" alt="AnalogCoder" width="120">
</p>

This repository contains the official implementation of the AAAI 2025 paper:

**AnalogCoder: Analog Circuit Design via Training-Free Code Generation**

**Authors:**  
[Yao Lai](https://laiyao1.github.io/)<sup>1</sup>,
[Sungyoung Lee](https://brianlsy98.github.io/)<sup>2</sup>,
[Guojin Chen](https://gjchen.me/)<sup>3</sup>,
[Souradip Poddar](https://www.linkedin.com/in/souradip-poddar-52376212a/)<sup>2</sup>,
[Mengkang Hu](https://aaron617.github.io/)<sup>1</sup>,
[David Z. Pan](https://users.ece.utexas.edu/~dpan/)<sup>2</sup>,
[Ping Luo](http://luoping.me/)<sup>1</sup>

<sup>1</sup> The University of Hong Kong  
<sup>2</sup> The University of Texas at Austin  
<sup>3</sup> The Chinese University of Hong Kong  

<p align="center">
  <a href="https://mmlab.hk/" target="_blank">
    <img src="hkummlab.png" alt="HKU MMLab" width="260"/>
  </a>
  &nbsp;&nbsp;&nbsp;
  <a href="https://www.cerc.utexas.edu/utda/" target="_blank">
    <img src="utda.jpg" alt="UTDA" width="180"/>
  </a>
</p>



## 🏆 Highlights

- **AAAI 2025 Oral Presentation** (Top 5%)
- **AAAI 2025 Top-15 Influential Papers** [[Rank 11](https://resources.paperdigest.org/2025/09/most-influential-aaai-papers-2025-09-version/)]

**Links:** [[Paper](https://arxiv.org/pdf/2405.14918)]

> **NEW RELEASE**  
> An extended version, **AnalogCoder-Pro**, is available:  
> [[Paper](https://arxiv.org/abs/2508.02518)] [[Repo](https://github.com/laiyao1/AnalogCoderPro)]



## Introduction

<p align="center">
  <img src="teaser.png" alt="AnalogCoder teaser" width="800">
</p>

**Analog circuit design** is a critical component of modern chip development. It involves selecting device types, defining connectivity, and tuning parameters to meet functional and performance requirements. While LLMs have shown strong capabilities in **digital** design tasks, analog design remains challenging due to the **complexity** of circuits and the **scarcity of high-quality data**.

To address these challenges, we introduce **AnalogCoder**, the *first* **training-free** LLM agent for analog circuit design that formulates design as **Python code generation**.

### Key advantages

- **Feedback-enhanced agentic workflow** with domain-specific prompts for robust autonomous design.
- A **circuit skill library** that archives successful designs as reusable modular subcircuits, enabling easier composition of complex systems.
- Extensive evaluation on a curated benchmark of **24** analog circuit design tasks shows that AnalogCoder successfully designed **20** circuits, outperforming existing baselines.

In summary, AnalogCoder helps reduce the labor intensity of analog chip design and enables non-experts to design analog circuits more efficiently.



## Evaluation of LLMs

**Ranking rule:** higher **#Solved** (successfully solved circuit design tasks) ranks first. If tied, higher **Avg. Pass@1** ranks first.

| LLM Model                          | Avg. Pass@1 | Avg. Pass@5 | #Solved |
|------------------------------------|------------:|------------:|--------:|
| Llama2-7B                          |         0.0 |         0.0 |       0 |
| Llama2-13B                         |         0.0 |         0.0 |       0 |
| SemiKong-8B*                       |         0.1 |         0.7 |       1 |
| Llama3-8B                          |         0.1 |         0.7 |       1 |
| Phi3-14B                           |         0.3 |         1.3 |       1 |
| Qwen-1.5-110B                      |         0.3 |         1.4 |       2 |
| CodeLlama-13B                      |         0.6 |         2.5 |       2 |
| Mistral-7B                         |         3.3 |         7.7 |       2 |
| Llama 2-70B                        |         5.1 |         9.8 |       3 |
| CodeQwen-1.5-7B                    |         1.1 |         5.6 |       4 |
| CodeLlama-34B                      |         1.9 |         7.4 |       4 |
| CodeLlama-7B                       |         2.4 |         9.0 |       4 |
| DeepSeek-Coder-33B                 |         4.0 |        10.2 |       4 |
| Llama3.1-8B                        |         4.9 |        12.9 |       4 |
| Magicoder-7B                       |         3.8 |         8.6 |       5 |
| Mixtral-8×7B                       |         5.6 |        12.4 |       5 |
| StarCoder2-15B-Instruct            |         5.6 |        12.4 |       5 |
| CodeGeeX4-9B*                      |        10.6 |        20.3 |       6 |
| CodeLlama-70B                      |         3.2 |        12.2 |       7 |
| CodeGemma-7B                       |         6.9 |        17.0 |       7 |
| WizardCoder-33B                    |         7.1 |        16.9 |       7 |
| GPT-3.5 (w/o context)              |         8.1 |        18.5 |       7 |
| GPT-3.5 (w/o flow)                 |        12.8 |        25.3 |       8 |
| Codestral-22B                      |        16.4 |        29.1 |       8 |
| GPT-3.5 (w/o CoT)                  |        19.4 |        26.3 |       8 |
| GLM-4                              |        22.8 |        31.2 |       8 |
| GPT-3.5 (SPICE)                    |        13.9 |        26.9 |       9 |
| GPT-3.5                            |        21.4 |        35.0 |      10 |
| GPT-3.5 (fine-tune)                |        28.1 |        39.6 |      10 |
| Llama3-70B                         |        28.8 |        36.4 |      11 |
| Gemini-1.0-Pro                     |        28.9 |        41.2 |      11 |
| Gemini-1.5-Flash                   |        35.7 |        40.6 |      11 |
| Qwen-2-72B                         |         9.3 |        26.6 |      12 |
| GPT-4o-mini                        |        34.9 |        41.7 |      12 |
| DeepSeek-V2-Chat                   |        38.6 |        44.3 |      13 |
| GPT-4 (w/o tool)                   |        51.1 |        57.7 |      14 |
| Llama3.1-70B                       |        25.4 |        42.6 |      14 |
| GPT-4o (w/o tool)                  |        54.2 |        58.9 |      15 |
| Claude-3.5-Sonnet (w/o tool)       |        58.1 |        60.7 |      15 |
| Mistral-Large-2                    |        28.6 |        51.0 |      17 |
| Gemini-1.5-Pro                     |        33.9 |        44.6 |      17 |
| DeepSeek-V2-Coder                  |        56.5 |        69.2 |      19 |
| Llama3.1-405B                      |        56.9 |        70.7 |      20 |
| **AnalogCoder (GPT-4o-based)**     |        66.1 |        75.9 |      20 |
| **AnalogCoder (Claude-3.5-based)** |        76.1 |        86.3 |      22 |

\* Without CoT (prompting the model to directly generate code rather than explicit device-level reasoning) due to token limitations or model specialization.

**Notes**
1. All results are reproducible.
2. The core Python environment setup does **not** require sudo privileges.  
   (However, installing system dependencies such as `ngspice` or `ollama` may require admin permissions depending on your OS.)



## Installation

AnalogCoder requires:
- **Python** ≥ 3.10  
- **PySpice** ≥ 1.5  
- **openai** ≥ 1.16.1  
- **ngspice** (as the SPICE backend)

### Option A: Install via `environment.yml` (recommended)

```bash
git clone https://github.com/laiyao1/AnalogCoder.git
cd AnalogCoder
conda env create -f environment.yml
conda activate analog
```

### Option B: Manual installation

```bash
git clone https://github.com/laiyao1/AnalogCoder.git
cd AnalogCoder

conda create -n analog python=3.11 -y
conda activate analog

pip install matplotlib pandas numpy scipy ollama openai

# SPICE backend (recommended via conda-forge)
conda install -c conda-forge ngspice -y

# PySpice
git clone https://github.com/PySpice-org/PySpice.git
cd PySpice
pip install -e .
cd ..
```



## (Optional) Ollama Setup (for local open-source LLMs)

> This section is only needed if you want to run open-source LLMs locally.

1) Install Ollama (Linux)

```bash
sudo apt-get update
sudo apt-get install -y zstd
curl -fsSL https://ollama.com/install.sh | sh
```

2) Start the Ollama server

```bash
nohup ollama serve > ollama.log 2>&1 &
```

3) Pull a model (example: `qwen3-coder`)

```bash
ollama pull qwen3-coder
```



## Environment Check

To verify your environment:

```bash
cd sample_design
python test_all_sample_design.py
```

If the output contains `All tasks passed`, your environment is ready.

If it prints `Please check your environment and try again`, please re-check your Python environment—especially `PySpice` and `ngspice` related setup.



## Quick Start

### Run with OpenAI models

```bash
python gpt_run.py --task_id=1 --api_key="[OPENAI_API_KEY]" --num_per_task=1
```

This generates **one** circuit solution for task 1.

### Run with a local open-source model (Ollama)

Make sure `ollama serve` is running first, then:

```bash
python gpt_run.py --model qwen3-coder --task_id=1
```



## Benchmark

- Task descriptions: `problem_set.tsv`
- Sample circuits: `sample_design/`
- Testbenches / checking scripts: `problem_check/`



## License

This project is licensed under the [MIT License](LICENSE).

## Citation

If you find this work useful, please cite:

```bibtex
@article{lai2025analogcoder,
    title={AnalogCoder: Analog Circuit Design via Training-Free Code Generation},
    volume={39},
    DOI={10.1609/aaai.v39i1.32016},
    number={1},
    journal={Proceedings of the AAAI Conference on Artificial Intelligence},
    author={Lai, Yao and Lee, Sungyoung and Chen, Guojin and Poddar, Souradip and Hu, Mengkang and Pan, David Z. and Luo, Ping},
    year={2025},
    pages={379-387}
}
```



## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=laiyao1/AnalogCoder&type=date&legend=top-left)](https://www.star-history.com/#laiyao1/AnalogCoder&type=date&legend=top-left)

## Testing different local models and recording experiments

The commands below run the **AnalogCoder-Pro 28-task benchmark** added to this
fork. The original `gpt_run.py` workflow above uses a different benchmark; keep
their results separate. Run these commands in Bash or Zsh from the repository
root, the directory containing `README.md` and `baselines/`.

### 1. Prepare the environment

For a fresh checkout on macOS with Homebrew, `uv`, and Ollama installed:

```sh
git clone https://github.com/KaneYin/Automated-SPICE-Code-Generation.git
cd Automated-SPICE-Code-Generation
brew install ngspice
uv venv --python 3.10 .venv
UV_CACHE_DIR=.cache/uv uv pip install --python .venv/bin/python -r baselines/analogcoder_pro/requirements.lock
```

For an existing checkout with this environment already prepared, skip the clone
and installation steps. Start Ollama with its desktop app, or run `ollama serve`
in a separate terminal if the server is not running. The default endpoint is
`http://127.0.0.1:11434`.

```sh
ollama list
.venv/bin/python baselines/analogcoder_pro/check_environment.py
.venv/bin/python -m unittest discover -s tests -v
```

The environment check runs real ngspice positive/negative controls without
requesting model inference. It saves its logs in
`runs/analogcoder_pro/environment-check/`. Unit tests also make no model requests.

Choose an exact installed model name, including its tag, from `ollama list`:

```sh
LOCAL_MODEL="qwen3.5:9b"
ollama show "$LOCAL_MODEL"
```

To test another model, change `LOCAL_MODEL` to its exact installed name. If it is
not installed yet, explicitly download your chosen tag with
`ollama pull "$LOCAL_MODEL"`. The launcher itself never downloads models.
The recorded baseline uses `qwen3.5:9b` (9.7B parameters, Q4_K_M), not a 7B model.

### 2. Run a three-task pilot first

Use the same text-only settings across models, including models without vision:

```sh
set -o pipefail
MODEL_LABEL="$(printf '%s' "$LOCAL_MODEL" | tr '/:' '__')"
RUN_LABEL="${MODEL_LABEL}-text-pilot-$(date +%Y%m%d-%H%M%S)"
RUN_DIR="runs/analogcoder_pro/$RUN_LABEL"
mkdir -p runs/analogcoder_pro

.venv/bin/python baselines/analogcoder_pro/run_local.py \
  --model "$LOCAL_MODEL" \
  --tasks 1 6 10 --trials 1 --max-generations 3 \
  --temperature 0.5 --seed 42 --context 16384 --max-tokens 4096 \
  --no-vision --out "$RUN_DIR" \
  2>&1 | tee "${RUN_DIR}.console.log"
```

Tasks 1, 6, and 10 exercise a common-source amplifier, an NMOS inverter, and a
low-pass filter. Each attempt permits an initial generation plus at most two
repairs. `--out` must name a **new directory**: create only its parent, not
`$RUN_DIR` itself. The launcher refuses an existing output directory.

For a vision-enabled experiment, omit `--no-vision` only when the model supports
vision, and use a new run label such as `${MODEL_LABEL}-vision-pilot-<timestamp>`.
The launcher checks that capability. The October 14 full baseline enabled vision;
the text-only commands here are a separate comparison condition. `--thinking`
enables separate thinking for supported models; record it as a separate condition.

### 3. Run all 28 tasks after the pilot

Keep the chosen model and settings, but use a new output directory:

```sh
RUN_LABEL="${MODEL_LABEL}-text-full-$(date +%Y%m%d-%H%M%S)"
RUN_DIR="runs/analogcoder_pro/$RUN_LABEL"

.venv/bin/python baselines/analogcoder_pro/run_local.py \
  --model "$LOCAL_MODEL" \
  --tasks all --trials 1 --max-generations 3 \
  --temperature 0.5 --seed 42 --context 16384 --max-tokens 4096 \
  --no-vision --out "$RUN_DIR" \
  2>&1 | tee "${RUN_DIR}.console.log"
```

The previous full run took about 137 minutes. Different models and repairs can
change runtime substantially. Increase `--trials` only for a deliberately larger
experiment. Keep task set, trials, context/output limits, generation budget,
vision/thinking settings, and temperature consistent when comparing models.
Raising the 4,096-token output cap is a new experiment, not a replacement for the
existing baseline. Acceptance means the public upstream checker passed.

### 4. Compare multiple installed models

Edit the model list before running this pilot sweep. Replace the placeholder with
a real installed tag; do not leave it in the command:

```sh
LOCAL_MODELS=("qwen3.5:9b" "replace-with-your-second-installed-model:tag")
mkdir -p runs/analogcoder_pro
set -o pipefail

for LOCAL_MODEL in "${LOCAL_MODELS[@]}"; do
  MODEL_LABEL="$(printf '%s' "$LOCAL_MODEL" | tr '/:' '__')"
  RUN_LABEL="${MODEL_LABEL}-text-pilot-$(date +%Y%m%d-%H%M%S)"
  RUN_DIR="runs/analogcoder_pro/$RUN_LABEL"
  if .venv/bin/python baselines/analogcoder_pro/run_local.py \
    --model "$LOCAL_MODEL" \
    --tasks 1 6 10 --trials 1 --max-generations 3 \
    --temperature 0.5 --seed 42 --context 16384 --max-tokens 4096 \
    --no-vision --out "$RUN_DIR" \
    2>&1 | tee "${RUN_DIR}.console.log"; then
    .venv/bin/python baselines/analogcoder_pro/report.py "$RUN_DIR"
  else
    printf 'Run needs inspection: %s\n' "$RUN_DIR"
  fi
done
```

An exit code of zero means no harness errors; it does not mean every circuit
passed. Inspect each run's pass counts and failure diagnostics in its report.

### 5. Inspect results and save the experiment summary

For a single run, keep `$RUN_DIR` set to the directory being inspected. These
commands read saved results and do not repeat inference:

```sh
.venv/bin/python baselines/analogcoder_pro/status.py "$RUN_DIR"
.venv/bin/python baselines/analogcoder_pro/report.py "$RUN_DIR"
.venv/bin/python -m usage_accounting.cli aggregate "$RUN_DIR"
```

`status.py` can also be run from another terminal during execution. In that
terminal, first set `RUN_DIR` to the same run path. `report.py` creates or replaces
`$RUN_DIR/REPORT.md`; accounting commands rebuild derived usage exports.

| Location | What to keep there | Commit to GitHub? |
| --- | --- | --- |
| `runs/analogcoder_pro/<run-id>/` | All raw experiment artifacts; one directory per invocation | No, ignored by Git |
| `runs/analogcoder_pro/<run-id>.console.log` | Launcher output captured by `tee` | No |
| `<run-directory>/manifest.json`, `model_info.json` | Exact model digest, server/environment, configuration, runtime instrumentation | No |
| `<run-directory>/results.json`, `results.csv`, `REPORT.md` | Per-attempt status, pass counts, timings, and readable diagnostics | No |
| `<run-directory>/api_calls/`, `task_<id>_trial_<n>.log`, `work/` | Native requests/responses, execution logs, generated circuits, figures/checker artifacts | No |
| `<run-directory>/usage/` | Per-call/stage/task/component counts, cache coverage, cost estimates and snapshots | No |
| [`EXPERIMENT_LOG.md`](EXPERIMENT_LOG.md) | Concise experiment status, model/digest/settings, passes, usage, observations | Yes |
| [`IMPLEMENTATION_LOG.md`](IMPLEMENTATION_LOG.md) | Code changes, design decisions, validation, limitations | Yes |

Add one experiment entry before updating its generated accounting block. For the
run currently selected in `$RUN_DIR`, append this heading **once**:

```sh
RUN_LABEL="${RUN_DIR##*/}"
printf '\n## Run: %s\n\n- Model: `%s`.\n- Raw artifacts (local only): `%s`.\n' \
  "$RUN_LABEL" "$LOCAL_MODEL" "$RUN_DIR" >> EXPERIMENT_LOG.md

.venv/bin/python -m usage_accounting.cli log-update "$RUN_DIR" \
  --log EXPERIMENT_LOG.md --run-name "$RUN_LABEL"
```

Complete the human-written entry with date, status, purpose, exact model digest
from `manifest.json`, settings, pass/failed/error counts, and observations. The
`log-update` command fills only the marked usage block and preserves other prose;
it does not automatically add model metadata or update the top summary table.
For a sweep, repeat this step for each run, with its matching `LOCAL_MODEL`.
Raw-artifact paths in the log are local-only because `runs/` is not published.

Ollama cache reuse uses provider-reported cached prompt tokens, with measurement
coverage. Fine prompt-component token counts stay unknown unless an optional local
tokenizer is configured, and then remain estimates. Local API charges are zero;
electricity/machine costs require explicit assumptions. To supply them, copy and
edit [`config/usage_pricing.example.json`](config/usage_pricing.example.json),
then pass `--usage-pricing <your-prices.json>` to the launcher or
`--pricing <your-prices.json>` to offline accounting commands. See the
[usage guide](docs/USAGE_ACCOUNTING.md) for the schema, optional tokenizer setup,
and the original runner's opt-in telemetry.
