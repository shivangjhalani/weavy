from weavy.models.canonical import (
    TranscriptSegment,
    extract_transcript_span,
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


def test_extract_transcript_span_returns_plain_text_for_untimed_transcript() -> None:
    segments = parse_transcript_text("This transcript has no inline timestamps.")

    assert extract_transcript_span(segments, start_offset=30, end_offset=45) == (
        "This transcript has no inline timestamps."
    )
