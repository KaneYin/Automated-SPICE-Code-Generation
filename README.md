# Automated-SPICE-Code-Generation
This is the repo of the project on an fully automated SPICE code generation framework with optimazition on performance-cost tradeoffs


## Some resources from Prof.
- https://github.com/JBlocklove/LLMs-for-EDA-Tutorial
- https://github.com/ACADLab/SPICEPilot

## Other References

### 1. SPICE / Analog Circuit Design

#### 1.1 Circuit Generation and Automated Repair

- AnalogCoder, AAAI 2025: Analog Circuit Design via Training-Free Code Generation
  - Relevant topics: PySpice code generation, simulation-guided repair, and reusable subcircuit libraries.
  - [Paper](https://arxiv.org/abs/2405.14918)
  - [GitHub](https://github.com/laiyao1/AnalogCoder)

- AnalogCoder-Pro: Unifying Analog Circuit Generation and Optimization via Multi-modal LLMs
  - Relevant topics: topology generation, device sizing, waveform-based diagnosis, and automated repair.
  - [Paper](https://arxiv.org/abs/2508.02518)
  - [GitHub](https://github.com/laiyao1/AnalogCoderPro)

- AnalogAgent: Self-Improving Analog Circuit Design Automation with LLM Agents
  - Relevant topics: multi-agent collaboration, execution feedback, and storage and retrieval of design experience.
  - [Paper](https://arxiv.org/abs/2603.23910)

#### 1.2 Circuit Sizing and Cost Efficiency

- LASO-BOSS: LLM-driven Analog Sizing Optimization via Bayesian Optimization and Sizing Strategies
  - Relevant topics: LLM-generated sizing strategies, numerical search through Bayesian optimization, and reduced LLM usage.
  - [Publication Page](https://www.sony.com/en/SonyInfo/technology/publications/laso-boss-llm-driven-analog-sizing-optimization-via-bayesian-optimization-and-sizing-strategies/)

#### 1.3 Circuit Benchmarks and Verification

- NetlistBench: Evaluating LLM Reliability in SPICE Netlist Recognition and Manipulation
  - Relevant topics: netlist recognition, connectivity and parameter edits, hierarchical operations, and structure preservation.
  - [Paper](https://arxiv.org/abs/2608.12197)
  - [GitHub](https://github.com/WoshiMayou/NetlistBench)

- AnalogGym: An Open and Practical Testing Suite for Analog Circuit Synthesis
  - Relevant topics: circuit sizing, specification satisfaction, and optimization efficiency.
  - [Paper](https://arxiv.org/abs/2409.08534)
  - [GitHub](https://github.com/CODA-Team/AnalogGym)

### 2. LLM Methods

#### 2.1 Model Routing and Cascades: Which Model to Use

- FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance
  - Relevant topics: model cascades that balance response quality and inference cost.
  - [Paper](https://arxiv.org/abs/2305.05176)

- RouteLLM: Learning to Route LLMs with Preference Data
  - Relevant topics: selecting between stronger and cheaper models based on the query to balance quality and cost.
  - [Paper](https://arxiv.org/abs/2406.18665)

#### 2.2 Multi-Turn Agent Routing: When to Switch Models

- Budget-Aware Agentic Routing via Boundary-Guided Training
  - Relevant topics: step-by-step selection between cheaper and more expensive models under task-level budget constraints.
  - [Paper](https://arxiv.org/abs/2602.21227)

- MTRouter: Cost-Aware Multi-Turn LLM Routing with History-Model Joint Embeddings
  - Relevant topics: estimating candidate model utility from interaction history for cost-aware multi-turn routing.
  - [Paper](https://arxiv.org/abs/2604.23530)

#### 2.3 Inference Budget Allocation: How Much Compute to Spend

- Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters
  - Relevant topics: allocating inference-time computation according to task difficulty, including search and iterative refinement.
  - [Paper](https://arxiv.org/abs/2408.03314)

#### 2.4 Prompt Compression: Reducing Input Tokens

- LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression
  - Relevant topics: prompt and context compression. Applications to SPICE require verification that node names, units, numerical values, and connectivity information remain intact.
  - [Paper](https://aclanthology.org/2024.findings-acl.57/)
  - [GitHub](https://github.com/microsoft/LLMLingua)
