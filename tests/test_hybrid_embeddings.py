import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_photo_sorter import hybrid_embeddings as hybrid


class _Photo:
    def __init__(self, path: Path):
        self.path = path


class HybridEmbeddingTests(unittest.TestCase):
    def test_cosine_and_conservative_decisions(self):
        self.assertAlmostEqual(1.0, hybrid._cosine([1, 0], [1, 0]))
        self.assertAlmostEqual(0.0, hybrid._cosine([1, 0], [0, 1]))
        self.assertEqual("same_candidate", hybrid._decision(0.95, same=0.90, different=0.50))
        self.assertEqual("different_candidate", hybrid._decision(0.40, same=0.90, different=0.50))
        self.assertEqual("ambiguous", hybrid._decision(0.70, same=0.90, different=0.50))

    def test_invalid_threshold_order_is_rejected(self):
        with patch.dict(
            os.environ,
            {"HYBRID_SIMILARITY_SAME": "0.5", "HYBRID_SIMILARITY_DIFFERENT": "0.8"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "different < same"):
                hybrid._settings()

    def test_preflight_only_requires_fastembed_when_feature_enabled(self):
        with patch.dict(os.environ, {"HYBRID_EMBEDDINGS": "false"}, clear=False), patch.object(
            hybrid, "fastembed_available", return_value=False
        ):
            self.assertEqual("", hybrid._preflight_error())
        with patch.dict(os.environ, {"HYBRID_EMBEDDINGS": "true"}, clear=False), patch.object(
            hybrid, "fastembed_available", return_value=False
        ):
            self.assertIn("FastEmbed", hybrid._preflight_error())
            self.assertIn("local-embeddings", hybrid._preflight_error())

    def test_analyze_photos_creates_adjacent_shadow_candidates(self):
        photos = [_Photo(Path("a.jpg")), _Photo(Path("b.jpg")), _Photo(Path("c.jpg"))]
        vectors = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]
        with (
            patch.object(hybrid, "_embed_paths", return_value=vectors),
            patch.dict(
                os.environ,
                {
                    "HYBRID_SIMILARITY_SAME": "0.9",
                    "HYBRID_SIMILARITY_DIFFERENT": "0.5",
                    "HYBRID_EMBEDDING_MODEL": "test-vision",
                },
                clear=False,
            ),
        ):
            session = hybrid.analyze_photos(photos)
        self.assertEqual(3, session.photo_count)
        self.assertEqual(2, len(session.candidates))
        self.assertEqual("same_candidate", session.candidates[0].decision)
        self.assertEqual("different_candidate", session.candidates[1].decision)
        self.assertEqual("test-vision", session.model)

    def test_shadow_evidence_is_non_routing_and_scores_optional_product_groups(self):
        session = hybrid.ShadowSession(
            model="test-vision",
            photo_count=4,
            elapsed_seconds=0.5,
            same_threshold=0.9,
            different_threshold=0.5,
            candidates=[
                hybrid.BoundaryCandidate("a.jpg", "b.jpg", 0.95, "same_candidate"),
                hybrid.BoundaryCandidate("b.jpg", "c.jpg", 0.30, "different_candidate"),
                hybrid.BoundaryCandidate("c.jpg", "d.jpg", 0.70, "ambiguous"),
            ],
            batch_size=16,
            parallel=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = [
                {"path": root / "a.jpg", "same_product_as_previous": False},
                {"path": root / "b.jpg", "same_product_as_previous": True},
                {"path": root / "c.jpg", "same_product_as_previous": False},
                {"path": root / "d.jpg", "same_product_as_previous": True},
            ]
            truth = root / "expected.csv"
            truth.write_text(
                "filename,category,product_group\n"
                "a.jpg,mouse,p1\n"
                "b.jpg,mouse,p1\n"
                "c.jpg,keyboard,p2\n"
                "d.jpg,keyboard,p2\n",
                encoding="utf-8",
            )
            summary = hybrid._write_shadow_evidence(items, root, session, truth)
            self.assertFalse(summary["routing_enabled"])
            self.assertAlmostEqual(2 / 3, summary["confident_coverage"])
            self.assertEqual(1.0, summary["agreement_with_sorter"])
            self.assertTrue(summary["ground_truth_product_groups_available"])
            self.assertEqual(2, summary["ground_truth_confident_pairs"])
            self.assertEqual(1.0, summary["ground_truth_confident_accuracy"])
            self.assertTrue((root / "hybrid_embedding_shadow.csv").is_file())
            payload = json.loads(
                (root / "hybrid_embedding_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual("shadow", payload["mode"])
            self.assertIn("ground_truth_confident_accuracy", payload["note"])

    def test_legacy_ground_truth_without_product_group_remains_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "expected.csv"
            path.write_text("filename,category,view\na.jpg,mouse,front\n", encoding="utf-8")
            self.assertEqual({}, hybrid._load_ground_truth_groups(path))

    def test_cli_flags_are_consumed_and_ground_truth_is_retained(self):
        captured = {}
        truth = Path("expected.csv")

        def base_parse(env_file):
            captured["argv"] = list(sys.argv)
            return argparse.Namespace(ground_truth=truth)

        module = SimpleNamespace(parse_args=base_parse)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                sys,
                "argv",
                [
                    "product-sorter",
                    "--hybrid-embeddings",
                    "--hybrid-embedding-model",
                    "Qdrant/clip-ViT-B-32-vision",
                    "--hybrid-same-threshold",
                    "0.91",
                    "--dry-run",
                ],
            ),
        ):
            hybrid._install_cli_flags(module)
            args = module.parse_args(Path(".env"))
            self.assertTrue(args.hybrid_embeddings)
            self.assertEqual("true", os.environ["HYBRID_EMBEDDINGS"])
            self.assertEqual("0.91", os.environ["HYBRID_SIMILARITY_SAME"])
            self.assertEqual(truth, module.HYBRID_GROUND_TRUTH_PATH)
            self.assertEqual(["product-sorter", "--dry-run"], captured["argv"])

    def test_benchmark_markdown_distinguishes_accuracy_from_diagnostic_agreement(self):
        text = hybrid._benchmark_markdown_section(
            {
                "model": "clip-test",
                "embedding_seconds": 2.0,
                "photos_per_second": 25.0,
                "confident_coverage": 0.8,
                "agreement_with_sorter": 0.9,
                "ground_truth_confident_accuracy": 0.85,
                "ground_truth_confident_pairs": 20,
                "ambiguous_pairs": 2,
            }
        )
        self.assertIn("Production routing: `disabled", text)
        self.assertIn("90.00%", text)
        self.assertIn("85.00%", text)
        self.assertIn("only labeled `product_group` boundaries", text)


if __name__ == "__main__":
    unittest.main()
