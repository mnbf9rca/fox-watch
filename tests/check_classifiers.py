"""Run real provider checks; invoke only through op run --env-file=.env.tpl."""
import argparse
import os
from pathlib import Path
import shlex

from foxcam.classify import classify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    for assignment in shlex.split((root / "vps/foxcam.env.example").read_text(), comments=True):
        key, value = assignment.split("=", 1)
        os.environ.setdefault(key, value)
    fixtures = root / "tests/fixtures"
    if args.failure:
        answer = classify("deepinfra/__foxcam_nonexistent_model__", [fixtures / "fox.jpg"] * 2)
        assert answer == ("unclassified", 0.0, ""), answer
        print("Invalid model: unclassified, confidence=0.0 (PASS)")
        return
    models = os.environ["MODELS"].split(",")
    assert all(models), "MODELS must not be empty"
    failed = []
    for model in models:
        for animal in ("fox", "hedgehog"):
            label, confidence, description = classify(model, [fixtures / f"{animal}.jpg"] * 2)
            print(f"{model}: expected={animal}, observed={label}, confidence={confidence}, description={description!r}", flush=True)
            if label == "unclassified":
                failed.append((model, animal))
    assert not failed, f"Failed model/image checks: {failed}"


if __name__ == "__main__":
    main()
