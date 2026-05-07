# Logic & Legacy: 2026 Inverted Index Engine
# We bypass the official Elasticsearch library to build the core algorithm
# that makes it so blindingly fast: The Inverted Index.

import re
from collections import defaultdict
from typing import List, Set, Dict

class InvertedIndex:
    """
    The core data structure behind Elasticsearch and Apache Lucene.
    Instead of mapping Documents -> Words, it maps Words -> Documents.
    """
    def __init__(self):
        # A dictionary mapping a 'token' (word) to a Set of Document IDs.
        # Format: {"python": {1, 4, 5}, "fast": {2, 4}}
        self.index: Dict[str, Set[int]] = defaultdict(set)
        
        # A mock "database" to hold the actual document payloads
        self.documents: Dict[int, str] = {}
        
        # Extremely basic stop words to ignore (the real ES does this natively)
        self.stop_words = {"the", "is", "at", "which", "on", "and", "a", "an", "to"}

    def _tokenize(self, text: str) -> List[str]:
        """Strips punctuation, lowercases, and splits text into raw tokens."""
        text = text.lower()
        # Keep only alphanumeric characters and spaces
        clean_text = re.sub(r'[^a-z0-9\s]', '', text)
        tokens = clean_text.split()
        return [t for t in tokens if t not in self.stop_words]

    def add_document(self, doc_id: int, text: str):
        """
        The Indexing Phase.
        We rip the document apart into tokens. We take every token and add 
        the Document ID to that token's set in our master index.
        """
        self.documents[doc_id] = text
        tokens = self._tokenize(text)
        
        for token in tokens:
            self.index[token].add(doc_id)
            
        print(f"[INDEXER] Document {doc_id} analyzed and mapped.")

    def search(self, query: str) -> List[str]:
        """
        The Query Phase.
        We do NOT scan the documents. We tokenize the query, look up the sets 
        in our O(1) dictionary, and find the intersection of those sets.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        print(f"\n[SEARCH] Query: '{query}' -> Tokens: {query_tokens}")

        # 1. Fetch the Set of Doc IDs for the FIRST token.
        first_token = query_tokens[0]
        matching_doc_ids = self.index.get(first_token, set())

        # 2. For multi-word queries, find the INTERSECTION of sets.
        # If searching "fast python", a doc MUST be in both the "fast" set and "python" set.
        for token in query_tokens[1:]:
            token_doc_ids = self.index.get(token, set())
            # Mathematical intersection operator (&)
            matching_doc_ids = matching_doc_ids & token_doc_ids

        # 3. Retrieve the actual payloads from the mock database
        results = [self.documents[doc_id] for doc_id in matching_doc_ids]
        
        print(f"[SEARCH] Found {len(results)} matches in O(1) index lookups.")
        return results


# ==========================================
# EXECUTION SIMULATION
# ==========================================
if __name__ == "__main__":
    engine = InvertedIndex()
    
    print("--- 1. BUILDING THE INDEX ---")
    engine.add_document(1, "Python is a great language for backend architecture.")
    engine.add_document(2, "Elasticsearch uses an inverted index to be extremely fast.")
    engine.add_document(3, "The router maps a URL to a specific python function.")
    engine.add_document(4, "Fast backend routing requires a radix tree, not regex.")
    engine.add_document(5, "Python and Elasticsearch combined create a fast architecture.")

    print("\n--- 2. EXECUTING FULL-TEXT SEARCH ---")
    
    # Search 1: Single word
    results_1 = engine.search("python")
    for r in results_1:
        print(f"  -> {r}")

    # Search 2: Multi-word (Intersection)
    results_2 = engine.search("fast architecture")
    for r in results_2:
        print(f"  -> {r}")
        
    # Search 3: Multi-word (No matches)
    results_3 = engine.search("python router tree")
    for r in results_3:
        print(f"  -> {r}")

"""
=========================================
EXPECTED TERMINAL OUTPUT
=========================================
--- 1. BUILDING THE INDEX ---
[INDEXER] Document 1 analyzed and mapped.
[INDEXER] Document 2 analyzed and mapped.
[INDEXER] Document 3 analyzed and mapped.
[INDEXER] Document 4 analyzed and mapped.
[INDEXER] Document 5 analyzed and mapped.

--- 2. EXECUTING FULL-TEXT SEARCH ---

[SEARCH] Query: 'python' -> Tokens: ['python']
[SEARCH] Found 3 matches in O(1) index lookups.
  -> Python is a great language for backend architecture.
  -> The router maps a URL to a specific python function.
  -> Python and Elasticsearch combined create a fast architecture.

[SEARCH] Query: 'fast architecture' -> Tokens: ['fast', 'architecture']
[SEARCH] Found 1 matches in O(1) index lookups.
  -> Python and Elasticsearch combined create a fast architecture.

[SEARCH] Query: 'python router tree' -> Tokens: ['python', 'router', 'tree']
[SEARCH] Found 0 matches in O(1) index lookups.
"""
