"""Derive a structured repair state from the upstream conversation.

Everything here is deterministic and uses only text the harness already
produced (model answers and templated feedback). No model call is needed to
build or maintain the state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

# Failure classes ordered by how far the candidate got through the pipeline.
# A higher rank means more checks were passed before the failure.
RANK = {
    "NO_CODE": 0,
    "UNKNOWN": 1,
    "PYTHON_ERROR": 1,
    "TIMEOUT": 1,
    "SIMULATION_FAILURE": 2,
    "FLOATING_NODE": 2,
    "NODE_NAMING": 3,
    "OPERATING_POINT": 3,
    "DC_SWEEP_NO_RESPONSE": 4,
    "FUNCTION_CHECK": 4,
}
LAYER = {
    "NO_CODE": "OUTPUT_FORMAT",
    "UNKNOWN": "UNKNOWN",
    "PYTHON_ERROR": "PYTHON_API",
    "TIMEOUT": "PYTHON_API",
    "SIMULATION_FAILURE": "NETLIST",
    "FLOATING_NODE": "NETLIST",
    "NODE_NAMING": "NETLIST",
    "OPERATING_POINT": "BIAS",
    "DC_SWEEP_NO_RESPONSE": "BEHAVIOR",
    "FUNCTION_CHECK": "BEHAVIOR",
}
# What a candidate has already demonstrated when it fails at a given rank.
VERIFIED_BY_RANK = {
    2: ["Python code runs without exception"],
    3: ["Python code runs without exception", "simulation converges (no floating nodes)"],
    4: ["Python code runs without exception", "simulation converges (no floating nodes)",
        "node names and device operating regions pass the static checks"],
}
INSTRUCTION = {
    "OUTPUT_FORMAT": "The previous reply contained no complete code block. "
                     "Keep the explanation brief so the reply is not cut off, "
                     "and write the complete code in one ```python block.",
    "PYTHON_API": "This is a Python/PySpice usage error, not a circuit topology problem. "
                  "Fix the failing statement and keep the topology unchanged. "
                  "Rewrite the complete corrected code.",
    "NETLIST": "The netlist is structurally wrong for the simulator or the checker. "
               "Fix the connections and rewrite the complete corrected code.",
    "BIAS": "The devices are not in their intended operating regions. "
            "Fix the bias voltages or connections and rewrite the complete corrected code.",
    "BEHAVIOR": "The circuit simulates but does not behave as required. "
                "Fix the topology or component values and rewrite the complete corrected code.",
    "UNKNOWN": "Fix the problem described in the evidence and rewrite the complete corrected code.",
}

_CODE_BLOCK = re.compile(r"```.*?\n(.*?)```", re.DOTALL)
_BEST_VOLTAGE = re.compile(r"According to dc sweep analysis, the best input voltage is ([^\s]+?)\. Please use this voltage\.\n?")
_FLOATING = re.compile(r"has one floating node: (\S+?), causing an error")
_NOISE = re.compile(r"Unsupported Ngspice version \d+|Warning: can't find the initialization file spinit\.")
_PYTHON_EXCEPTION = re.compile(r"^\w+(?:\.\w+)*(?:Error|Exception): ", re.MULTILINE)
_SIMULATOR = re.compile(r"singular matrix|timestep too small|simulation failed|analysis failed|fatal error|"
                        r"command 'run' failed|no such vector", re.IGNORECASE)
_PATH = re.compile(r"(?:/[^\s/\"']+)+/([^\s/\"']+)")
_EXCEPTION = re.compile(r"^(\w+(?:\.\w+)*(?:Error|Exception|Exit|Interrupt)\b.*)$", re.MULTILINE)
_BOILERPLATE = [
    "I am encountering an error when running the PySpice code. Below is the error message:",
    "Identify any structural errors in this circuit's topology (e.g., missing components, incorrect connections) "
    "and rewrite the complete corrected code from scratch, with each modification clearly marked and explained in comments.",
    "According to the operating point check, there are some issues, which defy the general operating principles of MOSFET devices.",
    "Please help me fix the issues and rewrite the corrected complete code.",
    "Please rewrite the corrected complete code.",
    "Please check the netlist and rewrite the complete code.",
    "Please identify the cause of the floating node and rewrite the corrected complete code.",
    "Please consider connect it to a voltage or current source or another device.",
]
MAX_EVIDENCE_LINES = 15
MAX_LINE_CHARS = 200


@dataclass
class Attempt:
    """One generated candidate and the harness verdict on it."""
    index: int
    answer: str
    feedback: str
    code: str = ""
    error_class: str = "UNKNOWN"
    evidence: str = ""
    affected_nodes: list = field(default_factory=list)
    facts: list = field(default_factory=list)

    @property
    def layer(self):
        return LAYER[self.error_class]

    @property
    def rank(self):
        return RANK[self.error_class]

    @property
    def headline(self):
        """Last informative evidence line; used in the ledger and signature."""
        lines = [line for line in self.evidence.splitlines() if line.strip()]
        exceptions = _EXCEPTION.findall(self.evidence)
        if exceptions:
            return exceptions[-1].strip()[:MAX_LINE_CHARS]
        # Prefer the line that states the verdict over a preamble line.
        for pattern in (r"fatal error", r"\bFAIL", r"singular matrix", r"does not|is not|NOT "):
            for line in lines:
                if re.search(pattern, line, re.IGNORECASE if pattern.islower() else 0):
                    return line.strip()[:MAX_LINE_CHARS]
        return (lines[0] if lines else "").strip()[:MAX_LINE_CHARS]

    @property
    def signature(self):
        """Stable identity of a failure, ignoring numbers that vary between runs."""
        return self.error_class + ":" + re.sub(r"\d+(?:\.\d+)?", "N", self.headline)


def extract_code(answer):
    """Mirror the upstream rule: the last fenced block is the candidate."""
    matches = _CODE_BLOCK.findall(answer or "")
    if not matches:
        return ""
    return "\n".join(line for line in matches[-1].split("\n") if line.strip())


def _clip(text):
    lines = [line.rstrip()[:MAX_LINE_CHARS] for line in text.splitlines() if line.strip()]
    if len(lines) > MAX_EVIDENCE_LINES:
        # Tracebacks carry the cause at the end; checker output at the start.
        head = MAX_EVIDENCE_LINES // 3
        lines = lines[:head] + ["... (truncated)"] + lines[-(MAX_EVIDENCE_LINES - head - 1):]
    return "\n".join(lines)


def _traceback_evidence(text):
    """Keep the innermost frame and the exception; drop absolute paths."""
    lines = text.splitlines()
    if not any(line.startswith("Traceback") for line in lines):
        return text  # e.g. a SyntaxError report, which has no frames to trim
    start = max(i for i, line in enumerate(lines) if line.startswith("Traceback"))
    before, trace = lines[:start], lines[start:]
    frames = [i for i, line in enumerate(trace) if line.lstrip().startswith("File ")]
    kept = trace[frames[-1]:] if frames else trace
    return "\n".join(before + kept)


def classify(feedback):
    """Map templated harness feedback to (class, evidence, nodes, facts)."""
    text = _NOISE.sub("", feedback or "")
    facts = []
    match = _BEST_VOLTAGE.search(text)
    if match:
        facts.append(f"DC sweep found the best input bias voltage: {match.group(1)} V")
        text = _BEST_VOLTAGE.sub("", text)
    nodes = []
    if "There is no complete code in your reply" in text:
        return "NO_CODE", "", nodes, facts
    floating = _FLOATING.search(text)
    if floating:
        nodes = [floating.group(1)]
        return "FLOATING_NODE", f"singular matrix: node {nodes[0]} is floating (no DC path that fixes its voltage)", nodes, facts
    execution = "I am encountering an error when running the PySpice code" in text
    rewrite_request = "Please rewrite the corrected complete code." in text
    # Classify on the evidence only; the templates themselves contain words like "error".
    evidence = text
    for phrase in _BOILERPLATE:
        evidence = evidence.replace(phrase, "")
    if "changing the input voltage does not change the output voltage" in text:
        error_class = "DC_SWEEP_NO_RESPONSE"
    elif "is not found in the netlist" in text:
        error_class = "NODE_NAMING"
        nodes = re.findall(r"node \(([^)]+)\) is not found", text)
    elif "According to the operating point check" in text:
        error_class = "OPERATING_POINT"
    elif execution:
        if "Time out error" in evidence or "Avoid letting users input" in evidence:
            error_class = "TIMEOUT"
        elif "Traceback (most recent call last)" in evidence or _PYTHON_EXCEPTION.search(evidence):
            error_class = "PYTHON_ERROR"
        elif _SIMULATOR.search(evidence) or re.search(r"\bERROR\b", evidence):
            error_class = "SIMULATION_FAILURE"
        else:
            error_class = "FUNCTION_CHECK"
    elif evidence.strip():
        error_class = "FUNCTION_CHECK" if rewrite_request else "UNKNOWN"
    else:
        error_class = "UNKNOWN"
    if error_class == "PYTHON_ERROR":
        evidence = _traceback_evidence(evidence)
    evidence = _PATH.sub(r"\1", evidence)
    return error_class, _clip(evidence), nodes, facts


def parse_attempts(messages):
    """Split [system?, task, answer0, feedback0, answer1, feedback1, ...].

    Returns (prefix messages up to and including the task prompt, attempts).
    Raises ValueError when the conversation does not have the repair shape.
    """
    first_assistant = next((i for i, m in enumerate(messages) if m["role"] == "assistant"), None)
    if first_assistant is None or first_assistant == 0:
        raise ValueError("No prior answer in conversation")
    prefix, tail = messages[:first_assistant], messages[first_assistant:]
    if len(tail) % 2 or any(not isinstance(m["content"], str) for m in messages):
        raise ValueError("Conversation is not alternating text answer/feedback turns")
    attempts = []
    for index in range(0, len(tail), 2):
        answer, feedback = tail[index], tail[index + 1]
        if answer["role"] != "assistant" or feedback["role"] != "user":
            raise ValueError("Conversation is not alternating answer/feedback turns")
        error_class, evidence, nodes, facts = classify(feedback["content"])
        attempts.append(Attempt(index // 2, answer["content"], feedback["content"], extract_code(answer["content"]),
                                error_class, evidence, nodes, facts))
    return prefix, attempts


def _statements(code):
    """Circuit-building statements, comments and blank lines removed."""
    result = []
    for line in code.splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith(("from ", "import ")):
            result.append(line)
    return result


def describe_change(previous_code, code, limit=4):
    """Summarize what a candidate changed relative to the one before it."""
    if not code:
        return "no code produced"
    if not previous_code:
        return "wrote a new design"
    before, after = _statements(previous_code), _statements(code)
    added = [line for line in after if line not in before]
    removed = [line for line in before if line not in after]
    if not added and not removed:
        return "resubmitted the same code"
    if len(added) + len(removed) > max(len(before), 1) * 0.8:
        return "rewrote most of the design"
    parts = [f"+ {line[:100]}" for line in added[:limit]] + [f"- {line[:100]}" for line in removed[:limit]]
    hidden = len(added) + len(removed) - len(parts)
    if hidden > 0:
        parts.append(f"(and {hidden} more changed lines)")
    return "; ".join(parts)


def best_attempt(attempts):
    """Highest-rank attempt that has code; later attempts win ties."""
    with_code = [a for a in attempts if a.code]
    if not with_code:
        return None
    return max(with_code, key=lambda a: (a.rank, a.index))


def repeated_failure(attempts):
    """True when the last two attempts failed in the same way."""
    return len(attempts) >= 2 and attempts[-1].signature == attempts[-2].signature
