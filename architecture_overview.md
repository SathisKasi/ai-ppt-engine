# AI PowerPoint Generator: Exhaustive Architecture & Workflow

This document provides a highly detailed, module-by-module breakdown of the application's architecture. It covers the micro-design decisions, caching mechanisms, JSON logging, data transformations, and the specific configurations applied to the LLM.

---

## 1. High-Level Pipeline & State Management

The application is built around a unidirectional data flow. Data transforms continuously from unstructured text into a fully mapped PowerPoint presentation. 

### Session State Caching Mechanism
Streamlit re-runs the entire Python script on every UI interaction. To prevent re-running expensive LLM calls or losing the generated PowerPoint, we employ robust **In-Memory Caching** via `st.session_state`.
- **File Upload Cache**: When a document is uploaded, the parsed text, detected structural tree, and raw bytes are cached. If the user changes a UI slider (like "Number of Slides"), the app doesn't re-parse the 100-page PDF; it retrieves the structure from cache.
- **Analysis Cache**: The raw output from the LLM (the JSON slide plan and the binary PPTX bytes) are cached in `st.session_state.pptx_bytes` and `st.session_state.presentation_plan`. This allows the user to immediately download the file without re-generating it.

---

## 2. Exhaustive Module Breakdown (Start to End)

### Module 1: `config.py` & `.env` (Environment & Thresholds)
**Design:** Centralized immutable configuration. 
- **Multi-Key Setup**: Parses a comma-separated list of Groq API keys (`GROQ_API_KEYS=key1,key2`) into a Python list to bypass rate limits.
- **Chunking Thresholds**: Sets strict token-to-character limits (e.g., `LLM_MAX_CHUNK_CHARS=8000`). If a semantic section exceeds this, the chunker knows to forcibly split it. `LLM_MIN_SECTION_CHARS` ensures tiny sub-headings are merged to save API calls.

### Module 2: `app.py` (Frontend & Orchestration)
**Design:** Streamlit UI with isolated pipeline modes.
- **Dual-Mode Input**: Detects if the user uploaded a file (triggers semantic pipeline) or typed a prompt (triggers legacy single-pass pipeline).
- **Security Design**: API keys entered in the UI are processed securely (password masked, stored only in the local session, never printed back to the screen). 
- **Progress Tracking Callback**: Passes a `_progress` callback function down into the core engines. As the backend analyzes chunks, it fires the callback to instantly update the UI.
- **Debug Expander**: Exposes the internal state of the `AnalysisCache` and chunking tree to the user in the UI for transparency.

### Module 3: `core/document_parser.py` (Text Extraction)
**Design:** Format-agnostic text extraction.
- **PDF Processing**: Uses `PyPDF2` to read binary streams.
- **DOCX Processing**: Uses `python-docx` to iterate through paragraphs.
- **TXT**: Uses strict `utf-8` decoding.
- **Micro-decision**: Normalizes all whitespace and strips null bytes before passing text further down the pipeline to prevent LLM tokenization errors.

### Module 4: `core/document_structure.py` (Semantic Tree Engine)
**Design:** Hierarchical Node Tree structure (`DocumentSection` class).
- **Heading Detection**: Uses regex and markdown patterns (e.g., `#`, `1.0`, `Chapter X`) to identify headings in raw text.
- **LLM Fallback (Auto-Structure)**: If a document is a solid wall of text (no headings), this module fires a targeted prompt (`AUTO_STRUCTURE_PROMPT`) to the LLM asking it to return a JSON array of logical "split points" (start line/end line) to artificially construct a hierarchy.
- **Semantic Chunker**: A recursive algorithm that traverses the `DocumentSection` tree. It attempts to pack as many sibling sections into a single `SemanticChunk` as possible, right up until it hits the `LLM_MAX_CHUNK_CHARS` limit. This guarantees chunks are semantically whole (a heading and its paragraphs are never split abruptly).

### Module 5: `core/chunk_analyzer.py` (Rolling Context Cache)
**Design:** Stateful, rolling-window LLM processor.
- **The `AnalysisCache`**: As the LLM analyzes Chunk 1, it outputs a `ChunkAnalysis` JSON object. This object is stored in the `AnalysisCache`. 
- **Rolling Context Injection**: When analyzing Chunk 2, the analyzer pulls the `Summary` and `Key Points` from Chunk 1 out of the cache and injects them into the prompt for Chunk 2. This prevents the LLM from losing the plot in a massive document.
- **JSON Disk Logging Mechanism**: Every single chunk analysis is immediately serialized via `model_dump_json()` and saved to disk (`logs/llm/<run_id>/section_XYZ.json`). This acts as an audit trail and a secondary file-based cache for debugging.

### Module 6: `core/consolidator.py` (Synthesis)
**Design:** Map-Reduce architecture.
- Takes the list of individual chunk JSON summaries (the "Map" results) and pushes them into a massive context window.
- The LLM acts as the "Reducer", identifying overarching themes, merging overlapping statistics, and outputting the master `ContentAnalysis` schema.

### Module 7: `core/presentation_planner.py` (The Designer)
**Design:** Data mapping and constraints injection.
- It receives the master `ContentAnalysis` and reads `layout_metadata.json`.
- **Micro-decision**: The prompt explicitly forces the LLM to select from `layout_type` strings (like `COMPARISON`). It mandates that the LLM must only generate text for the exact placeholder keys defined in the metadata for that specific layout. 
- Outputs the master `PresentationPlan` JSON.

### Module 8: `core/pptx_builder.py` (Native Renderer)
**Design:** Object cloning and primitive drawing.
- **Avoids XML Corruption**: Instead of deep-copying corruptible XML tags from the template, the builder reads the layout, creates a brand new blank slide, applies the layout, and then explicitly maps the text strings into the `shape.text_frame.text` attributes.
- **Layout Mapping**: Matches the placeholder name provided by the LLM (e.g., `"left_content"`) to the actual `shape.name` on the slide layout.

---

## 3. LLM Configuration & JSON Handling

### Multi-Key Round-Robin Architecture
**Module:** `llm/key_manager.py`
- **The Problem:** Groq has strict Requests-Per-Minute (RPM) limits. A 50-page document might require 15 fast chunking calls, causing an immediate `429 Too Many Requests`.
- **The Solution:** The `KeyManager` is initialized with a pool of keys. 
- **Micro-design:** It uses modulo arithmetic: `selected_key = keys[chunk_index % num_keys]`. This means Chunk 1 uses Key A, Chunk 2 uses Key B, Chunk 3 uses Key A. It's fully deterministic and perfectly balances the load across the API keys without needing complex asynchronous throttling.

### JSON Schema Enforcement (Pydantic)
**Module:** `llm/schemas.py` & `llm/groq_client.py`
We do not rely on the LLM to format strings correctly. 
- **Structured Outputs**: The `GroqClient` appends `{ "type": "json_object" }` to the API request parameters.
- **Pydantic Validation**: Every LLM response is instantly parsed through a Pydantic model (e.g., `ChunkAnalysis.model_validate_json()`). 
- If the LLM misses a required field, Pydantic throws an exception, which triggers the `GroqClient`'s exponential backoff and retry loop to request the data again.

### Persistent JSON Auditing
Every step of the LLM's thought process is written to the local filesystem in JSON format under `logs/llm/<run_id>/`:
1. `document_structure.json`: The layout of the document headings.
2. `section_000.json`, `section_001.json`: The specific analysis and rolling context for each chunk.
3. `consolidation.json`: The final merged understanding of the document.
4. `presentation_plan.json`: The exact instructions sent to the PowerPoint builder.
This provides a complete, replayable history of how the AI generated the presentation.

---

## 4. LLM Agent Lifecycle & Interfaces

Throughout the application, the Groq LLM acts as an autonomous "agent" invoked at very specific checkpoints. Below is the exact lifecycle of when the agent is called, what it is asked to do, and the exact data structure it is forced to return.

### Call 1: Auto-Structure Inference (Optional)
* **When it is called**: Only in the Semantic Pipeline, and only if `document_structure.py` fails to find any explicit headings (e.g., `#` or `1.0`) in the uploaded document.
* **What it does**: The agent is given the raw text and asked to act as a structural parser to find logical break points.
* **Prompt Used**: `SYSTEM_ROLE_STRUCTURE_INFERRER` and `AUTO_STRUCTURE_PROMPT`.
* **What it Returns**: A JSON array of objects representing sections, strictly validated against the `DocumentStructureLog` Pydantic model:
  ```json
  {
    "sections": [
      { "heading": "Introduction", "start_line": 1, "end_line": 45 },
      { "heading": "Market Analysis", "start_line": 46, "end_line": 120 }
    ]
  }
  ```

### Call 2: Per-Chunk Analysis
* **When it is called**: In the Semantic Pipeline (`chunk_analyzer.py`), it is called recursively in a loop for every single semantic chunk in the document.
* **What it does**: The agent is given a specific chunk of text, plus the summarized context of all previous chunks. It acts as an analyst extracting key insights.
* **Prompt Used**: `SYSTEM_ROLE_CHUNK_ANALYST` and `CHUNK_ANALYSIS_PROMPT`.
* **What it Returns**: A JSON object detailing the chunk's contents, strictly validated against the `ChunkAnalysis` Pydantic model:
  ```json
  {
    "chunk_id": "section_1",
    "heading": "Market Analysis",
    "summary": "The market is growing at 15% CAGR...",
    "key_points": ["Point A", "Point B"],
    "statistics": ["15% CAGR", "$5B TAM"],
    "importance": "high"
  }
  ```

### Call 3: Consolidation (or Single-Pass Analysis)
* **When it is called**: 
  - *Semantic Pipeline*: Called once at the end by `consolidator.py` after all chunks are analyzed.
  - *Legacy Pipeline*: Called once by `content_analyzer.py` if the user entered a raw prompt (bypassing chunking entirely).
* **What it does**: The agent synthesizes all the fragmented chunk analyses (or the raw prompt) into a master overarching understanding of the presentation's goals.
* **Prompt Used**: `SYSTEM_ROLE_CONSOLIDATOR` and `CONSOLIDATION_PROMPT` (or `CONTENT_ANALYSIS_PROMPT` for legacy).
* **What it Returns**: A comprehensive JSON overview strictly validated against the `ContentAnalysis` Pydantic model:
  ```json
  {
    "topic": "Q3 Market Expansion Strategy",
    "key_themes": ["Growth", "Challenges"],
    "detected_types": ["COMPARISON", "STATISTICS", "PROCESS"],
    "target_audience_tone": "Professional and persuasive",
    "suggested_slide_count": 12
  }
  ```

### Call 4: Presentation Planning (The Final Output)
* **When it is called**: Called once by `presentation_planner.py` just before building the PPTX.
* **What it does**: The agent acts as a McKinsey-level presentation designer. It is given the `ContentAnalysis` (from Call 3) and the exact schema of the PowerPoint template from `layout_metadata.json`. It maps the insights into actual slides.
* **Prompt Used**: `SYSTEM_ROLE_PRESENTATION_EXPERT` and `PRESENTATION_PLAN_PROMPT`.
* **What it Returns**: A massive, highly-structured JSON object representing the exact slides and text placeholders to be drawn, validated against the `PresentationPlan` and `SlidePlan` Pydantic models:
  ```json
  {
    "title": "Q3 Expansion",
    "subtitle": "Navigating the New Market",
    "slides": [
      {
        "slide_number": 1,
        "layout_type": "TITLE_AND_CONTENT",
        "title": "Market Overview",
        "content": {
          "text": "The market presents significant opportunities.",
          "bullets": ["High Demand", "Low Competition"]
        }
      }
    ]
  }
  ```
