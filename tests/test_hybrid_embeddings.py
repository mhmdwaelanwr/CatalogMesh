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
        self.assertEqual(
            "same_candidate",
            hybrid._decision(0.95, same=0.90, different=0.50),
        )
        self.assertEqual(
            "different_candidate",
            hybrid._decision(0.40, same=0.90, different=0.50),
        )
        self.assertEqual(
            "ambiguous",
            hybrid._decision(0.70, same=0.90, different=0.50),
        )

    def test_invalid_threshold_order_is_rejected(self):
        with patch.dict(
            os.environ,
            {
                "HYBRID_SIMILARITY_SAME": "0.5",
                "HYBRID_SIMILARITY_DIFFERENT": "0.8",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "different < same"):
                hybrid._settings()

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

    def test_shadow_evidence_is_explicitly_non_routing(self):
        session = hybrid.ShadowSession(
            model="test-vision",
            photo_count=3,
            elapsed_seconds=0.5,
            same_threshold=0.9,
            different_threshold=0.5,
            candidates=[
                hybrid.BoundaryCandidate("a.jpg", "b.jpg", 0.95, "same_candidate"),
                hybrid.BoundaryCandidate("b.jpg", "c.jpg", 0.30, "different_candidate"),
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
            ]
            summary = hybrid._write_shadow_evidence(items, root, session)
            self.assertFalse(summary["routing_enabled"])
            self.assertEqual(1.0, summary["confident_coverage"])
            self.assertEqual(1.0, summary["agreement_with_sorter"])
            self.assertTrue((root / "hybrid_embedding_shadow.csv").is_file())
            payload = json.loads(
                (root / "hybrid_embedding_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual("shadow", payload["mode"])
            self.assertIn("not ground-truth accuracy", payload["note"])

    def test_cli_flags_are_consumed_and_persisted_to_environment(self):
        captured = {}

        def base_parse(env_file):
            captured["argv"] = list(sys.argv)
            return argparse.Namespace()

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
            self.assertEqual(["product-sorter", "--dry-run"], captured["argv"])

    def test_missing_optional_runtime_fails_preflight_only_when_enabled(self):
        module = SimpleNamespace(
            ensure_requirements=lambda: True,
            select_photo_sample=lambda photos, limit: photos,
            build_outputs=lambda *args, **kwargs: None,
            parse_args=lambda env_file: argparse.Namespace(),
        )
        with (
            patch.dict(os.environ, {"HYBRID_EMBEDDINGS": "true"}, clear=False),
            patch.object(hybrid, "fastembed_available", return_value=False),
        ):
            hybrid.apply_hybrid_embeddings(module)
            self.assertFalse(module.ensure_requirements())

    def test_benchmark_markdown_labels_agreement_as_diagnostic(self):
        text = hybrid._benchmark_markdown_section(
            {
                "model": "clip-test",
                "embedding_seconds": 2.0,
                "photos_per_second": 25.0,
                "confident_coverage": 0.8,
                "agreement_with_sorter": 0.9,
                "ambiguous_pairs": 2,
            }
        )
        self.assertIn("Production routing: `disabled", text)
        self.assertIn("90.00%", text)
        self.assertIn("not ground-truth accuracy", text)


if __name__ == "__main__":
    unittest.main()
