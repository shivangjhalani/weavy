from transcribe import (
    TranscriptSegment,
    extract_segment_range,
    parse_transcript_text,
)


def test_parse_transcript_text_parses_inline_timestamps() -> None:
    segments = parse_transcript_text(
        "[0:00] First line.\n[0:14] Second line.\n[0:28] Third line."
    )

    assert segments == [
        TranscriptSegment(start=0.0, end=14.0, text="First line."),
        TranscriptSegment(start=14.0, end=28.0, text="Second line."),
        TranscriptSegment(start=28.0, end=29.0, text="Third line."),
    ]


def test_parse_transcript_text_wraps_plain_text() -> None:
    segments = parse_transcript_text("This transcript has no inline timestamps.")

    assert segments == [
        TranscriptSegment(
            start=0.0,
            end=1.0,
            text="This transcript has no inline timestamps.",
        )
    ]


def test_extract_segment_range_returns_text_by_index() -> None:
    segments = parse_transcript_text(
        "[0:00] First line.\n[0:14] Second line.\n[0:28] Third line."
    )

    assert extract_segment_range(segments, 1, 2) == "Second line."
    assert (
        extract_segment_range(segments, 0, 3) == "First line. Second line. Third line."
    )
    assert extract_segment_range(segments, 0, 1) == "First line."


def test_extract_segment_range_plain_text() -> None:
    segments = parse_transcript_text("This transcript has no inline timestamps.")

    assert (
        extract_segment_range(segments, 0, 1)
        == "This transcript has no inline timestamps."
    )


def test_extract_segment_range_empty_on_out_of_bounds() -> None:
    segments = parse_transcript_text("[0:00] Only line.")

    assert extract_segment_range(segments, 5, 10) == ""
