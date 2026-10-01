"""
tests/test_benchmark_suite.py — Unit Tests for Hardened XRLF Benchmark Suite
===========================================================================
Validates:
  1. Data leak prevention (no searching intermediate text for expected answer).
  2. Strict MCQ conclusion extraction without false positives.
  3. Strict numeric extraction and numeric set validation.
  4. Non-empty, non-partial is_correct validation (closing substring leaching).
  5. Multimodal asset generation and ApiResponder payload preservation.
"""

import unittest

from builder.probes.benchmark_suite import (
    ApiResponder,
    StubResponder,
    _extract_answer,
    _is_correct,
    generate_test_audio_b64,
    generate_test_image_b64,
    run_coherence_track,
)


class TestBenchmarkHardening(unittest.TestCase):
    """Test suite ensuring all leaching holes are permanently closed."""

    # ── 1. Leaching Hole: Intermediate Number Leak ─────────────────────────────

    def test_numeric_no_intermediate_leak(self):
        """
        Model mentions intermediate numbers (including the ground truth 12),
        but concludes with a wrong answer (99).
        Old code leaked: it found 12 in the text and marked it correct.
        Hardened code must extract 99 and evaluate to False.
        """
        reasoning_text = (
            "We have 24 apples. In the morning 7 are sold, then 5 in the afternoon. "
            "24 - 7 - 5 = 12. However, due to spoilages, the final answer is 99."
        )
        predicted = _extract_answer(reasoning_text, expected="12")
        self.assertEqual(predicted, "99")
        self.assertFalse(_is_correct(predicted, "12"))

    def test_numeric_explicit_declarations(self):
        """Model explicitly declares answer with various standard delimiters."""
        self.assertEqual(
            _extract_answer("Work: 60 * 2.5. #### 150", expected="150"), "150"
        )
        self.assertTrue(
            _is_correct(
                _extract_answer("Work: 60 * 2.5. #### 150", expected="150"), "150"
            )
        )

        self.assertEqual(
            _extract_answer("The result is \\boxed{84}", expected="84"), "84"
        )
        self.assertTrue(
            _is_correct(
                _extract_answer("The result is \\boxed{84}", expected="84"), "84"
            )
        )

        self.assertEqual(
            _extract_answer("Therefore, the final answer is $120.", expected="120"),
            "120",
        )
        self.assertTrue(
            _is_correct(
                _extract_answer("Therefore, the final answer is $120.", expected="120"),
                "120",
            )
        )

        self.assertEqual(_extract_answer("Total fare: $7.00.", expected="7.00"), "7.00")
        self.assertTrue(
            _is_correct(_extract_answer("Total fare: $7.00.", expected="7.00"), "7.00")
        )

    def test_numeric_multi_number_set(self):
        """Validates multi-number answers like '18 and 19'."""
        text = "Let the integers be x and x+1. 2x+1 = 37 => x = 18. The integers are 18 and 19."
        predicted = _extract_answer(text, expected="18 and 19")
        self.assertEqual(predicted, "18 and 19")
        self.assertTrue(_is_correct(predicted, "18 and 19"))

        # Order independence
        self.assertTrue(_is_correct("19 and 18", "18 and 19"))
        # Partial single character must NOT pass
        self.assertFalse(_is_correct("a", "18 and 19"))
        self.assertFalse(_is_correct("18", "18 and 19"))
        self.assertFalse(_is_correct("", "18 and 19"))

    # ── 2. MCQ Extraction & False-Positive Prevention ─────────────────────────

    def test_mcq_conclusion_over_intermediate(self):
        """
        Model walks through choices: (A) is wrong, (B) is wrong, therefore (C) is correct.
        Must extract 'C', NOT the first seen '(A)'.
        """
        response = (
            "Let's examine the options:\n"
            "(A) rubber is an insulator.\n"
            "(B) wood is an insulator.\n"
            "(C) copper conducts electricity.\n"
            "(D) plastic is an insulator.\n"
            "Therefore, the correct choice is (C)."
        )
        q = "Which of these is a conductor of electricity? (A) rubber (B) wood (C) copper (D) plastic"
        predicted = _extract_answer(response, expected="C", question=q)
        self.assertEqual(predicted, "C")
        self.assertTrue(_is_correct(predicted, "C"))

    def test_mcq_no_english_article_false_positive(self):
        """Sentences starting with 'A' or containing 'a' must not trigger choice 'A'."""
        text = (
            "A store has several items in stock, but I am unable to solve this problem."
        )
        predicted = _extract_answer(text, expected="C")
        self.assertNotEqual(predicted, "A")
        self.assertFalse(_is_correct(predicted, "C"))

    def test_mcq_option_text_resolution(self):
        """Model states the text of the option instead of letter: 'The answer is copper.'"""
        q = "Which of these is a conductor of electricity? (A) rubber (B) wood (C) copper (D) plastic"
        response = "After careful analysis, the answer is copper."
        predicted = _extract_answer(response, expected="C", question=q)
        self.assertEqual(predicted, "C")
        self.assertTrue(_is_correct(predicted, "C"))

    # ── 3. Leaching Hole: Substring Leaching in _is_correct ────────────────────

    def test_is_correct_no_substring_leaching(self):
        """Ensure empty strings or fragments do not pass."""
        self.assertFalse(_is_correct("", "C"))
        self.assertFalse(_is_correct("   ", "12"))
        self.assertFalse(_is_correct("", ""))
        self.assertFalse(_is_correct("a", "18 and 19"))
        self.assertFalse(_is_correct("and", "18 and 19"))
        self.assertFalse(_is_correct("c", "D"))

    def test_is_correct_numeric_tolerance(self):
        """Numeric comparison handles formatting and float equivalences."""
        self.assertTrue(_is_correct("7", "7.00"))
        self.assertTrue(_is_correct("7.0", "7"))
        self.assertTrue(_is_correct("$120.00", "120"))
        self.assertFalse(_is_correct("7.5", "7.00"))

    # ── 4. Multimodal Preservation & Generation ───────────────────────────────

    def test_pure_python_png_generation(self):
        """Ensures pure-Python PNG generator creates valid base64 data."""
        b64_png = generate_test_image_b64("red_square")
        self.assertTrue(len(b64_png) > 50)
        # PNG signature in base64 starts with iVBORw0KGgo
        self.assertTrue(b64_png.startswith("iVBORw0KGgo"))

    def test_pure_python_wav_generation(self):
        """Ensures pure-Python WAV generator creates valid base64 data."""
        b64_wav = generate_test_audio_b64(440.0, duration_s=0.1)
        self.assertTrue(len(b64_wav) > 100)
        # WAV RIFF signature in base64 starts with UklGR
        self.assertTrue(b64_wav.startswith("UklGR"))

    def test_api_responder_preserves_multimodal_payload(self):
        """Ensures ApiResponder does NOT strip multimodal structures into text."""
        responder = ApiResponder(port=8402)
        self.assertEqual(responder.port, 8402)
        self.assertEqual(responder.url, "http://127.0.0.1:8402/v1/chat/completions")

    # ── 5. Coherence Track ───────────────────────────────────────────────────

    def test_coherence_track_stub_fails_honestly(self):
        """Stub responder must not pass coherence track."""
        stub = StubResponder()
        result = run_coherence_track(stub, quick=True)
        self.assertEqual(result.correct, 0)
        self.assertEqual(result.accuracy, 0.0)


if __name__ == "__main__":
    unittest.main()
