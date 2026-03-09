from __future__ import annotations

import unittest

from docdb.parser import parse_llms_text


class ParserTests(unittest.TestCase):
    def test_parses_markdown_links_and_sections(self) -> None:
        text = """
# Example

## Docs
- [Quickstart](https://example.com/docs/quickstart.md): Start here
- [API](https://example.com/docs/api.md)

## Optional
- [Website](https://example.com/)
        """.strip()

        docs = parse_llms_text(text, "https://example.com/llms.txt", "example")

        self.assertEqual(len(docs), 3)
        self.assertEqual(docs[0].section, "Docs")
        self.assertEqual(docs[0].title, "Quickstart")
        self.assertEqual(docs[0].description, "Start here")
        self.assertTrue(docs[0].is_markdown)
        self.assertEqual(docs[1].rel_path, "docs/api.md")
        self.assertFalse(docs[2].is_markdown)
        self.assertEqual(docs[2].section, "Optional")

    def test_parses_relative_and_bare_markdown_urls(self) -> None:
        text = """
## Docs
- [Reference](/docs/reference.md): Relative URL
Read more at https://example.com/docs/appendix.md
        """.strip()

        docs = parse_llms_text(text, "https://example.com/llms.txt", "example")

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].url, "https://example.com/docs/reference.md")
        self.assertEqual(docs[1].title, "Appendix")
        self.assertEqual(docs[1].rel_path, "docs/appendix.md")


if __name__ == "__main__":
    unittest.main()
