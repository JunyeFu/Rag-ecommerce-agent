"""Knowledge base ingestion and retrieval unit tests."""
import pytest
from app.services.ingestion import chunk_text, parse_document_file


@pytest.mark.unit
class TestChunkText:
    def test_short_text_single_chunk(self):
        chunks = chunk_text("This is a short text.")
        assert len(chunks) == 1
        assert "short text" in chunks[0]

    def test_empty_text(self):
        chunks = chunk_text("")
        assert chunks == []

    def test_paragraph_split(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = chunk_text(text, chunk_size=30)
        assert len(chunks) >= 2

    def test_large_text_multiple_chunks(self):
        para = "This is a paragraph with enough content to fill a chunk. " * 20
        text = para + "\n\n" + para
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        assert len(chunks) >= 2

    def test_whitespace_only(self):
        chunks = chunk_text("   \n\n  \n  ")
        assert chunks == []

    def test_overlap_preserves_context(self):
        para1 = "A" * 400
        para2 = "B" * 400
        text = para1 + "\n\n" + para2
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        assert len(chunks) >= 2


@pytest.mark.unit
class TestParseDocumentFile:
    def test_txt_file(self):
        content = parse_document_file(b"Hello world", "test.txt")
        assert content == "Hello world"

    def test_md_file(self):
        content = parse_document_file(b"# Header\n\nSome text", "doc.md")
        assert "Header" in content
        assert "Some text" in content

    def test_utf8_chinese(self):
        content = parse_document_file("你好世界".encode("utf-8"), "chinese.txt")
        assert content == "你好世界"

    def test_unsupported_type(self):
        with pytest.raises(ValueError, match="Unsupported"):
            parse_document_file(b"data", "file.xyz")

    def test_unsupported_docx(self):
        with pytest.raises(ValueError, match="Unsupported"):
            parse_document_file(b"data", "file.docx")
