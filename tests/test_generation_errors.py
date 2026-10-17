"""Offline regression coverage for the generation -> judge -> report handoff."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import report
import run_judge


class GenerationErrorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "example_model_outputs.jsonl"
        self.output = self.root / "example_rubric_verdicts.jsonl"
        network = patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected HTTP request"))
        network.start()
        self.addCleanup(network.stop)

    def row(self, item_id="example-1", response="blue", error=None):
        return {
            "item": {
                "id": item_id,
                "source_item_id": item_id,
                "use_case": "fixture",
                "prompt": "Return the word blue.",
                "verification_criteria": ["The response contains blue."],
            },
            "model_response": response,
            "error": error,
        }

    def reply(self, refused=False):
        return json.dumps({
            "score": 1,
            "pass": False,
            "refusal_detected": refused,
            "justification": "The response was evaluated against the fixture.",
            "criteria_scores": {
                "requirement_coverage": 5,
                "technical_correctness": 4,
                "actionability": 3,
            },
        })

    def judge(self, rows, *, reply=None, side_effect=None):
        self.source.write_text("".join(json.dumps(row) + "\n" for row in rows))
        args = [
            "run_judge.py", "--model-outputs", str(self.source),
            "--output", str(self.output), "--provider", "openrouter",
            "--api-key", "offline-fixture", "--concurrency", "1",
        ]
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
            with patch.object(run_judge, "openai_structured",
                              return_value=reply or self.reply(), side_effect=side_effect) as call:
                run_judge.main()
        records = [json.loads(line) for line in self.output.read_text().splitlines()]
        return records, call

    def assert_unscored(self, record):
        self.assertIsNone(record["score"])
        self.assertIsNone(record["pass"])
        self.assertIsNone(record["refusal_detected"])
        self.assertEqual(record["criteria_scores"], {})

    def test_generation_failure_does_not_call_judge(self):
        original_error = "TimeoutError: provider timed out"
        records, call = self.judge([self.row(response="", error=original_error)])

        call.assert_not_called()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assert_unscored(record)
        self.assertIn("Generation", record["error"])
        self.assertIn(original_error, record["error"])
        self.assertEqual(record["id"], "example-1")
        self.assertEqual(record["source_item_id"], "example-1")
        self.assertEqual(record["use_case"], "fixture")

    def test_generation_error_takes_precedence_over_partial_response(self):
        original_error = "IncompleteRead: response was truncated"
        records, call = self.judge([self.row(response="partial output", error=original_error)])

        call.assert_not_called()
        self.assert_unscored(records[0])
        self.assertIn(original_error, records[0]["error"])

    def test_successful_answer_keeps_weighted_scoring(self):
        records, call = self.judge([self.row(response="reasoning\n</think>\nblue")])

        call.assert_called_once()
        messages = call.call_args.args[3]
        self.assertEqual(json.loads(messages[1]["content"])["model_response"], "blue")
        self.assertEqual(records[0]["score"], 4.3)
        self.assertTrue(records[0]["pass"])
        self.assertFalse(records[0]["refusal_detected"])
        self.assertIsNone(records[0]["error"])

    def test_explicit_refusal_still_scores_zero(self):
        records, call = self.judge([self.row(response="I cannot answer.")], reply=self.reply(refused=True))

        call.assert_called_once()
        self.assertEqual(records[0]["score"], 0)
        self.assertFalse(records[0]["pass"])
        self.assertTrue(records[0]["refusal_detected"])
        self.assertTrue(all(value == 0 for value in records[0]["criteria_scores"].values()))
        self.assertIsNone(records[0]["error"])

    def test_empty_response_without_generation_error_still_reaches_judge(self):
        records, call = self.judge([self.row(response="")], reply=self.reply(refused=True))

        call.assert_called_once()
        self.assertTrue(records[0]["refusal_detected"])
        self.assertEqual(records[0]["score"], 0)
        self.assertIsNone(records[0]["error"])

    def test_judge_failure_remains_an_unscored_error(self):
        records, call = self.judge([self.row()], side_effect=TimeoutError("judge timed out"))

        call.assert_called_once()
        self.assert_unscored(records[0])
        self.assertEqual(records[0]["error"], "TimeoutError: judge timed out")

    def test_report_excludes_generation_failure_from_scored_metrics(self):
        replies = [self.reply(), self.reply(refused=True)]
        rows = [
            self.row("failed", response="", error="HTTPError: HTTP Error 429: Too Many Requests"),
            self.row("answered"),
            self.row("refused", response="I cannot answer."),
        ]
        records, call = self.judge(rows, side_effect=replies)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(len(records), 3)

        output = io.StringIO()
        with patch.object(sys, "argv", ["report.py", str(self.root)]), contextlib.redirect_stdout(output):
            report.main()
        model_row = next(line for line in output.getvalue().splitlines() if line.startswith("example "))
        fields = model_row.split()
        self.assertEqual(fields[1:], ["3", "50%", "50%", "2.15", "4.30", "1"])


if __name__ == "__main__":
    unittest.main()
