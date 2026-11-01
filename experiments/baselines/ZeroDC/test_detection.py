import json
import unittest

import numpy as np
import pandas as pd

from detection import (
    calculate_detection_metrics,
    cluster_by_cell_sample_kmeans,
    evaluate_rule_set,
    initialize_llm,
    parse_rule_response,
    run_dynamic_checker,
)


class DetectionTests(unittest.TestCase):
    def test_double_escaped_rule_newlines_are_normalized(self):
        escaped_code = (
            r"def fun1(df):\n"
            r"    return df['value'].astype(str).str.contains('x', na=False)"
        )
        response = f"```json\n{json.dumps({'fun1': escaped_code})}\n```"

        rules = parse_rule_response(response)

        self.assertIn("\n", rules["fun1"])
        frame = pd.DataFrame({"value": ["clean", "x-error"]})
        result = run_dynamic_checker(rules["fun1"], frame, "value.fun1")
        self.assertEqual([False, True], result.tolist())

    def test_rule_name_must_match_json_key(self):
        response = json.dumps({"fun1": "def wrong_name(df):\n    return []"})

        with self.assertRaisesRegex(ValueError, "Could not parse valid rules"):
            parse_rule_response(response)

    def test_metrics_use_boolean_complements(self):
        metrics = calculate_detection_metrics(
            prediction=[0, 1, 0, 1],
            ground_truth=[0, 1, 1, 0],
        )

        self.assertEqual(
            {"TP": 1, "FP": 1, "TN": 1, "FN": 1},
            {key: metrics[key] for key in ("TP", "FP", "TN", "FN")},
        )
        self.assertEqual(0.5, metrics["f1"])

    def test_kmeans_caps_clusters_at_distinct_embeddings(self):
        embeddings = np.ones((3, 1, 2), dtype=float)

        outliers, centers = cluster_by_cell_sample_kmeans(embeddings, 0)

        self.assertEqual(1, len(outliers))
        self.assertEqual(1, len(centers))

    def test_rule_set_evaluation_combines_rules(self):
        rules = {
            "fun1": "def fun1(df):\n    return df['value'].eq('a')",
            "fun2": "def fun2(df):\n    return df['value'].eq('b')",
        }
        frame = pd.DataFrame({"value": ["a", "b", "c"]})

        evaluation = evaluate_rule_set(rules, frame, "value")

        self.assertEqual((2, 3), evaluation["single_rule"].shape)
        self.assertEqual([True, True, False], evaluation["total_rule"].tolist())

    def test_empty_rule_set_detects_nothing(self):
        frame = pd.DataFrame({"value": ["a", "b", "c"]})
        evaluation = evaluate_rule_set({}, frame, "value")
        self.assertEqual((0, 3), evaluation["single_rule"].shape)
        self.assertEqual([False, False, False], evaluation["total_rule"].tolist())

    def test_llm_client_has_bounded_request_timeout(self):
        llm = initialize_llm(
            model_name="test-model",
            openai_api_base="https://example.invalid/v1",
            openai_api_key="test-key",
            temperature=0,
            request_timeout=12,
        )

        self.assertEqual(12, llm.request_timeout)
        self.assertEqual(0, llm.max_retries)


if __name__ == "__main__":
    unittest.main()
