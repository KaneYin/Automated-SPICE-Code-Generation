#!/usr/bin/env python3
"""Verify real ngspice and positive/negative controls for the inverter checker."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from run_local import HERE, ROOT, child_environment, simulator_check, verify_upstream


def main():
    verify_upstream()
    env = child_environment()
    destination = ROOT / "runs" / "analogcoder_pro" / "environment-check"
    destination.mkdir(parents=True, exist_ok=True)
    env["MPLCONFIGDIR"] = str(destination / "matplotlib")
    simulator_check(env, destination)
    prefix = """import sys
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
circuit = Circuit('Inverter checker control')
circuit.V('dd', 'Vdd', circuit.gnd, 5)
circuit.V('in', 'Vin', circuit.gnd, 1)
"""
    controls = {
        "resistive_load_nmos_inverter": ("""circuit.model('nmos_model', 'nmos', level=1, kp=100e-6, vto=0.5)
circuit.MOSFET('1', 'Vout', 'Vin', circuit.gnd, circuit.gnd, model='nmos_model', w=50e-6, l=1e-6)
circuit.R('load', 'Vdd', 'Vout', 1000)
""", 0),
        "noninverting_wire_negative_control": ("circuit.R('wire', 'Vin', 'Vout', 1)\n", 2),
    }
    checker = (HERE / "upstream" / "problem_check" / "Inverter.py").read_text()
    results = []
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        for name, (body, expected) in controls.items():
            script = Path(temporary) / f"{name}.py"
            script.write_text(prefix + body + "simulator = circuit.simulator()\n" + checker)
            process = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=60)
            (destination / f"{name}.log").write_text(process.stdout + process.stderr)
            results.append({"control": name, "expected_exit": expected, "actual_exit": process.returncode})
            assert process.returncode == expected, f"{name}: expected {expected}, got {process.returncode}; see {destination}"
            print(f"{name}: expected exit {expected}, got {process.returncode}")
    (destination / "controls.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"Environment checks passed. Logs: {destination}")


if __name__ == "__main__":
    main()
