"""Semantic search tool using embeddings."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class SemanticSearchTool(Tool):
    """Search codebase using semantic similarity."""

    @property
    def name(self) -> str:
        return "semantic_search"

    @property
    def description(self) -> str:
        return (
            "Search the codebase using natural language queries. "
            "Finds code by meaning, not just keywords. "
            "Requires an index (run `mistral index` first). "
            "Falls back to text search if no index exists."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language description of what you're looking for. "
                        "Example: 'authentication handling', 'database connection setup'."
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Defaults to 5.",
                },
            },
            "required": ["query"],
        }

    def execute(self, query: str, top_k: int = 5, **kwargs: Any) -> ToolResult:
        """Execute the semantic search.

        Args:
            query: Natural language query.
            top_k: Maximum results to return.

        Returns:
            ToolResult with search results or error.
        """
        try:
            from ..knowledge import CodebaseIndex, Embedder

            # Check if RAG is available
            if not Embedder.is_available():
                return self._fallback_search(query, top_k)

            # Try to use semantic search
            index = CodebaseIndex(str(Path.cwd()))
            stats = index.get_stats()

            if not stats:
                fallback_result = self._fallback_search(query, top_k)
                return ToolResult(
                    success=True,
                    output=(
                        "No semantic index found for this project. "
                        "Run `mistral index` to enable semantic search.\n"
                        "Falling back to text search...\n\n"
                        + fallback_result.output
                    ),
                    hint="Run `mistral index` to enable semantic search for better results.",
                )

            # Check for stale index
            if index.is_stale():
                stale_warning = (
                    "[Warning: Index may be outdated. Run `mistral index --rebuild` to refresh.]\n\n"
                )
            else:
                stale_warning = ""

            results = index.search(query, top_k=top_k)

            if not results:
                return ToolResult(True, f"No semantic matches found for: {query}")

            output_lines = [f"{stale_warning}Semantic search results for: {query}\n"]
            for i, result in enumerate(results, 1):
                output_lines.append(
                    f"[{i}] {result.file_path} "
                    f"(lines {result.line_start}-{result.line_end}, score: {result.score:.3f})"
                )
                # Show snippet
                snippet = result.chunk_text[:300]
                if len(result.chunk_text) > 300:
                    snippet += "..."
                # Indent the snippet
                indented_snippet = "\n    ".join(snippet.split("\n"))
                output_lines.append(f"    {indented_snippet}")
                output_lines.append("")

            return ToolResult(True, "\n".join(output_lines))

        except Exception as e:
            return ToolResult(False, "", f"Semantic search error: {e}")

    def _fallback_search(self, query: str, top_k: int) -> ToolResult:
        """Fall back to text-based search.

        Args:
            query: The search query.
            top_k: Maximum results.

        Returns:
            ToolResult from text search.
        """
        from .project import SearchFilesTool

        search_tool = SearchFilesTool()

        # Extract significant words for pattern matching
        # Skip common words
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "and",
            "but",
            "if",
            "or",
            "because",
            "until",
            "while",
            "what",
            "which",
            "who",
            "this",
            "that",
            "these",
            "those",
            "i",
            "me",
            "my",
            "we",
            "our",
            "you",
            "your",
            "he",
            "him",
            "his",
            "she",
            "her",
            "it",
            "its",
            "they",
            "them",
            "their",
        }

        words = [w.lower() for w in query.split() if w.lower() not in stop_words]
        pattern = words[0] if words else query.split()[0] if query.split() else query

        result = search_tool.execute(pattern=pattern, max_results=top_k)
        if result.success:
            result = ToolResult(
                success=True,
                output=f"[Text search fallback for '{pattern}']\n{result.output}",
                hint="Install sentence-transformers for semantic search: pip install mistral-cli[rag]",
            )
        return result
