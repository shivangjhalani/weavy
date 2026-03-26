import pytest


@pytest.mark.xfail(reason="Wave 0 stub — implementation pending")
def test_transcribe_file_accepts_audio_path():
    """TRNS-01: System accepts audio files and transcribes via Groq Whisper."""
    assert False


@pytest.mark.xfail(reason="Wave 0 stub — implementation pending")
def test_transcript_stored_with_id_and_timestamp():
    """TRNS-02: Raw transcript stored with unique ID, recording timestamp, and full text."""
    assert False


@pytest.mark.xfail(reason="Wave 0 stub — implementation pending")
def test_episode_spans_created_during_ingestion():
    """TRNS-03: Episode spans created during ingestion."""
    assert False
