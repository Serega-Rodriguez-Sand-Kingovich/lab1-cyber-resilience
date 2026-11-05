"""Local prediction demo; JSON input is size-checked BEFORE parsing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import load_and_check_data
from .inference import load_verified_model, predict_digits, predict_request

MAX_JSON_FILE_BYTES = 128 * 1024


def main() -> None:
    parser = argparse.ArgumentParser(description="Lab 2 secure digit classifier CLI")
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--demo", action="store_true", help="Use the first Lab 1 digit")
    commands.add_argument("--json", type=Path, help="A UTF-8 JSON file with a pixels field")
    args = parser.parse_args()
    model = load_verified_model()
    if args.demo:
        X, y, _ = load_and_check_data()
        prediction = predict_digits(model, X[0].reshape(8, 8))
        print(json.dumps({"actual_label": int(y[0]), "predicted_label": int(prediction[0])}))
        return
    if not args.json.is_file() or args.json.stat().st_size > MAX_JSON_FILE_BYTES:
        parser.error("JSON file must exist and must be 128 KiB or smaller")
    payload = json.loads(args.json.read_text(encoding="utf-8"))
    predictions = predict_request(model, payload)
    print(json.dumps({"predictions": predictions.tolist(), "count": len(predictions)}))


if __name__ == "__main__":
    main()
