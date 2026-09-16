"""
llm/prompts.py — All LLM prompt templates.

Prompts are plain Python strings with {placeholder} format variables.
They are filled using str.format(**kwargs) at call sites.

Design principles:
- Explicit grounding: tell the LLM to use only source content.
- Explicit JSON output format: reduces hallucination and parse failures.
- Explicit anti-hallucination rules.
- Separate prompts for each pipeline stage.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# System roles
# ---------------------------------------------------------------------------

SYSTEM_ROLE_ANALYST = """\
You are an expert presentation consultant and content analyst.
Your job is to extract and organize information from source documents to create
professional business presentations.

CRITICAL RULES:
- Use ONLY information present in the provided source content.
- Do NOT invent statistics, dates, names, or facts.
- Do NOT add information that is not in the source.
- If the user provides a general topic/prompt (not a document), that prompt IS the source.
- Return ONLY valid JSON. No markdown code fences. No explanatory text.
"""

SYSTEM_ROLE_PLANNER = """\
You are an expert presentation architect who creates structured, compelling presentations.
You convert content analysis into a detailed slide-by-slide presentation plan in JSON format.

CRITICAL RULES:
- Use ONLY facts from the provided source analysis and original content.
- Do NOT invent information not present in the source.
- Select the most appropriate layout for each slide based on its content type.
- Return ONLY valid JSON. No markdown code fences. No explanatory text.
- Ensure all JSON is valid and properly escaped.
"""

SYSTEM_ROLE_CONTENT = """\
You are a professional presentation copywriter who specializes in concise, impactful
business presentations.

CRITICAL RULES:
- Write concise, presentation-friendly content only.
- Use ONLY facts from the provided source content.
- Do NOT invent or expand upon information not in the source.
- Format bullet points as short, action-oriented phrases (max 10 words each).
- Return ONLY valid JSON. No markdown code fences. No explanatory text.
"""

# ---------------------------------------------------------------------------
# Stage 1 — Content Analysis
# ---------------------------------------------------------------------------

CONTENT_ANALYSIS_PROMPT = """\
Analyze the following source content and extract structured information for presentation creation.

SOURCE CONTENT:
{source_content}

USER REQUIREMENTS:
- Target Audience: {audience}
- Presentation Style: {style}
- Requested Slides: {slide_count}
- Language: {language}
- Additional Instructions: {additional_instructions}

Analyze the source and return a JSON object with this exact structure:
{{
  "main_topic": "The primary subject of the content",
  "key_concepts": ["concept1", "concept2", "..."],
  "sections": ["section or chapter title 1", "section 2", "..."],
  "statistics": ["important number or metric mentioned in source", "..."],
  "processes": ["process or workflow described in source", "..."],
  "comparisons": ["comparison or contrast described in source", "..."],
  "timelines": ["timeline, roadmap, or date sequence mentioned", "..."],
  "conclusions": ["key conclusion from the source", "..."],
  "recommendations": ["recommendation from the source", "..."],
  "suggested_slide_count": {suggested_slides},
  "content_types_detected": ["BULLETS", "STATS", "CARDS_2_COL", "..."],
  "summary": "2-3 sentence summary of the source content",
  "executive_highlights": [
    "One-liner executive takeaway #1 (max 12 words)",
    "One-liner executive takeaway #2 (max 12 words)",
    "One-liner executive takeaway #3 (max 12 words)"
  ],
  "agenda_topics": ["Major section topic 1", "Major section topic 2", "Major section topic 3"]
}}

RULES:
- executive_highlights: 3-5 crisp, high-impact one-liners summarising the most important takeaways.
  Use only facts from the source. Max 12 words each.
- agenda_topics: ordered list of the major section topics that will appear as body slides.
  Mirror the natural flow of the source content. Minimum 2, maximum 8 topics.
- Available content types to detect: TITLE, EXECUTIVE_SUMMARY, AGENDA, BULLETS, CARDS_2_COL,
  CARDS_3_COL, SECTION_HEADER, IMAGE_TEXT, TABLE, TIMELINE, STATS, CONCLUSION

Return ONLY the JSON object. No preamble. No explanation.
"""

# ---------------------------------------------------------------------------
# Stage 2 — Presentation Planning
# ---------------------------------------------------------------------------

PRESENTATION_PLANNING_PROMPT = """\
Create a complete presentation plan based on the content analysis below.

CONTENT ANALYSIS:
{content_analysis}

ORIGINAL SOURCE CONTENT (for reference — use ONLY this as your factual basis):
{source_content}

PRESENTATION REQUIREMENTS:
- Title: {presentation_title}
- Target Audience: {audience}
- Presentation Style: {style}
- Number of Slides: {slide_count}
- Language: {language}
- Additional Instructions: {additional_instructions}

SLIDE COUNT RULES (adapt structure to the requested number of slides):
  If slide_count <= 5:
    - SKIP EXECUTIVE_SUMMARY and AGENDA to leave room for real content
    - Structure: TITLE → SECTION_HEADER (optional) → 2-3 CONTENT slides → CONCLUSION
  If slide_count 6-8:
    - Include EXECUTIVE_SUMMARY (slide 2) but make AGENDA optional
    - Structure: TITLE → EXEC_SUMMARY → CONTENT slides → CONCLUSION
  If slide_count >= 9 (standard):
    - Full structure is MANDATORY: TITLE → EXECUTIVE_SUMMARY → AGENDA → SECTION_HEADERs + CONTENT → CONCLUSION
    - SECTION_HEADER MUST precede each major topic block

VISUAL ARCHETYPES — Choose the one that BEST MATCHES what the content looks like visually:

  TITLE             → Full-screen cover slide with large title & subtitle.
                      USE ONLY for slide 1. Never repeat.
                      Required fields: subtitle

  EXECUTIVE_SUMMARY → Two-panel slide: LEFT=purpose statement, RIGHT=3-5 key highlights.
                      USE ONLY for slide 2 in standard decks (see slide count rules above).
                      Required fields: highlights (list of 3-5 one-liners max 12 words each),
                                       purpose_statement (one sentence describing the goal)
                      Optional fields: key_metric (single impactful number, e.g. "23.3% perf gain")

  AGENDA            → Numbered cards showing major presentation sections.
                      USE ONLY for slide 3 in standard decks (see slide count rules above).
                      Required fields: agenda_items (list of section titles, 2-8 items,
                                       must match the SECTION_HEADER slide titles in the body)

  BULLETS           → Title bar + vertical list of 5-8 bullet points.
                      DEFAULT for general information, overviews, key points.
                      Required fields: bullets (list of strings, max 10 words each)
                      Optional fields: body_text (prose fallback if no bullets)

  SECTION_HEADER    → Bold chapter/section divider with large text.
                      REQUIRED before every major topic block in the body.
                      Required fields: section_title, description

  CARDS_2_COL       → Two side-by-side content panels / comparison cards.
                      Use when content has exactly TWO topics, options, or approaches.
                      Required fields: left_heading, left_bullets (list), right_heading, right_bullets (list)

  CARDS_3_COL       → Three side-by-side cards (steps, pillars, or phases).
                      Use ONLY when content has exactly 3 steps, phases, or pillars.
                      Required fields: steps (list of {{step_number, title, description}})

  TABLE             → Title + structured data table with rows and columns.
                      Use when content has a matrix, capability grid, or comparison table.
                      Required fields: table_data with headers (list) and rows (list of lists)

  STATS             → 2-4 large KPI numbers / metric callouts with labels.
                      Use ONLY when content contains specific numbers, percentages, or benchmarks.
                      Required fields: statistics (list of {{value, label, context}})

  IMAGE_TEXT        → Image/diagram placeholder on left + text/bullets on right.
                      Use for architecture diagrams, system overviews, or visual concepts.
                      Required fields: description, bullets (list)

  TIMELINE          → Sequential milestone cards / awards / roadmap items.
                      Use for chronological dates, roadmaps, or sequential milestones.
                      Required fields: items (list of {{date, event, description}})

  CONCLUSION        → Summary + recommendations + next steps panel layout.
                      REQUIRED as the last content slide.
                      Required fields: summary_points (list), recommendations (list),
                                       next_steps (list), call_to_action (string)

LAYOUT SELECTION RULES:
- Use SECTION_HEADER at EVERY major topic transition in the body (at least one per agenda item)
- Use CARDS_2_COL when comparing two options, teams, approaches, or models
- Use CARDS_3_COL ONLY when content has exactly 3 discrete steps, phases, or pillars
- Use TABLE when content has structured rows/columns (capability matrix, comparison grid)
- Use STATS ONLY for slides with 2-4 specific numbers, percentages, or KPIs — not prose
- Use IMAGE_TEXT for architecture diagrams, technology stacks, or visual concepts
- Use TIMELINE for roadmaps, milestones, date sequences, or award lists
- Default to BULLETS for all other general information

SELECTION PRINCIPLE: Pick the archetype that matches the SHAPE of the content, not just the topic.
  Example: "3 security benchmarks scored 90%, 95%, 88%" → STATS (not BULLETS)
  Example: "Comparison of Model A vs Model B features" → CARDS_2_COL (not BULLETS)
  Example: "5-step onboarding process" → CARDS_3_COL or BULLETS (not PROCESS)
  Example: "Q1 launch, Q2 rollout, Q3 scale" → TIMELINE (not BULLETS)

Generate EXACTLY {slide_count} slides.

PER-ARCHETYPE CONTENT EXAMPLES (use EXACTLY these field names for each layout type):

EXECUTIVE_SUMMARY example:
  "content": {{
    "highlights": [
      "Model achieves 23.3% performance gain over prior generation",
      "100% score on cybersecurity ExploitBench benchmark",
      "Autonomous digital agency across enterprise software ecosystems"
    ],
    "purpose_statement": "Present Astra's capabilities and enterprise rollout plan for leadership decision-making.",
    "key_metric": "23.3% performance gain over GPT-5"
  }}

AGENDA example:
  "content": {{
    "agenda_items": [
      "Performance & Security Capabilities",
      "Enterprise Deployment Architecture",
      "Risk Analysis & Recommendations"
    ]
  }}

BULLETS example:
  "content": {{
    "bullets": [
      "Supports autonomous task execution across enterprise apps",
      "Context window expanded to 1 million tokens",
      "Integrated safety filters with real-time monitoring"
    ]
  }}

CARDS_2_COL example:
  "content": {{
    "left_heading": "Current State",
    "left_bullets": ["Manual processes", "High error rate", "Slow turnaround"],
    "right_heading": "Future State",
    "right_bullets": ["Automated workflows", "99.9% accuracy", "Real-time processing"]
  }}

STATS example:
  "content": {{
    "statistics": [
      {{"value": "23.3%", "label": "Performance Lead", "context": "vs prior model on SWE-bench"}},
      {{"value": "100%", "label": "ExploitBench Score", "context": "cybersecurity benchmark"}},
      {{"value": "1M", "label": "Token Context Window", "context": "enterprise document handling"}}
    ]
  }}

CONCLUSION example:
  "content": {{
    "summary_points": ["GPT-6 Astra leads on performance and security", "Enterprise rollout is low-risk"],
    "recommendations": ["Begin pilot with IT and finance departments Q1", "Establish AI governance framework"],
    "next_steps": ["Procure enterprise license", "Define pilot scope", "Train core team"],
    "call_to_action": "Thank You — Questions Welcome"
  }}

Return a JSON object with this EXACT structure:
{{
  "presentation": {{
    "title": "Presentation Title",
    "subtitle": "Optional subtitle",
    "slides": [
      {{
        "slide_number": 1,
        "purpose": "Cover slide",
        "title": "Presentation Title",
        "layout_type": "TITLE",
        "content": {{
          "subtitle": "Presentation subtitle"
        }},
        "speaker_notes": "Welcome and introduction"
      }},
      {{
        "slide_number": 2,
        "purpose": "Executive overview of key highlights",
        "title": "Executive Summary",
        "layout_type": "EXECUTIVE_SUMMARY",
        "content": {{
          "highlights": [
            "Key highlight one from source (max 12 words)",
            "Key highlight two from source (max 12 words)",
            "Key highlight three from source (max 12 words)"
          ],
          "purpose_statement": "One sentence describing the presentation goal"
        }},
        "speaker_notes": "High-level overview for decision makers"
      }},
      {{
        "slide_number": 3,
        "purpose": "Presentation agenda and flow",
        "title": "Agenda",
        "layout_type": "AGENDA",
        "content": {{
          "agenda_items": ["Section One", "Section Two", "Section Three"]
        }},
        "speaker_notes": "Walk the audience through what we will cover"
      }},
      {{
        "slide_number": 4,
        "purpose": "Section divider",
        "title": "Section One",
        "layout_type": "SECTION_HEADER",
        "content": {{
          "section_title": "Section One",
          "description": "Brief section overview"
        }}
      }},
      {{
        "slide_number": 5,
        "purpose": "Key content",
        "title": "Key Points",
        "layout_type": "BULLETS",
        "content": {{
          "bullets": [
            "Key point one from source",
            "Key point two from source"
          ]
        }},
        "speaker_notes": "Notes for the speaker"
      }},
      {{
        "slide_number": 6,
        "purpose": "Conclusion and recommendations",
        "title": "Conclusion & Recommendations",
        "layout_type": "CONCLUSION",
        "content": {{
          "summary_points": ["Key summary point one", "Key summary point two"],
          "recommendations": ["Recommendation one", "Recommendation two"],
          "next_steps": ["Next step one", "Next step two"],
          "call_to_action": "Call to action text"
        }},
        "speaker_notes": "Close with recommendations"
      }}
    ]
  }}
}}

CONTENT RULES:
- Bullets: max 8-10 words each, action-oriented
- Use only facts from the source content
- Each BULLETS slide should have 5-8 bullets
- EXECUTIVE_SUMMARY highlights: 3-5 one-liners, max 12 words each
- AGENDA agenda_items: must match SECTION_HEADER titles in the body slides
- CARDS_2_COL: must have left_heading, left_bullets, right_heading, right_bullets
- CARDS_3_COL: must have steps as list of {{step_number, title, description}}
- TABLE: must have table_data with headers (list) and rows (list of lists)
- STATS: must have statistics as list of {{value, label, context}}
- IMAGE_TEXT: must have description and bullets
- TIMELINE: must have items as list of {{date, event, description}}
- CONCLUSION: must have summary_points, recommendations, next_steps, call_to_action
- SECTION_HEADER: must have section_title and description

Return ONLY the JSON object. No preamble. No explanation. No markdown.
"""

# ---------------------------------------------------------------------------
# JSON correction / retry prompt
# ---------------------------------------------------------------------------

JSON_CORRECTION_PROMPT = """\
The JSON you previously returned had the following error:

ERROR: {error_message}

INVALID JSON (first 2000 chars):
{invalid_json}

Please return a corrected, valid JSON object that matches the required schema.
Fix ALL JSON syntax errors: missing commas, unclosed brackets, invalid escapes, etc.

Return ONLY the corrected JSON. No preamble. No explanation.
"""

# ---------------------------------------------------------------------------
# Slide content refinement (Stage 3 — optional per-slide polish)
# ---------------------------------------------------------------------------

SLIDE_CONTENT_REFINEMENT_PROMPT = """\
Refine the content for this presentation slide to make it more concise and impactful.

SLIDE DETAILS:
- Title: {slide_title}
- Layout: {layout_type}
- Purpose: {purpose}
- Current Content: {current_content}

SOURCE CONTENT (use ONLY facts from here):
{source_excerpt}

REQUIREMENTS:
- Target Audience: {audience}
- Style: {style}
- Language: {language}

Make the content:
1. More concise (bullets max 10 words)
2. More impactful and action-oriented
3. Better suited for visual presentation
4. Grounded in the source content only

Return the refined content as a JSON object matching the layout type's content schema.
Return ONLY the JSON. No preamble.
"""

# ---------------------------------------------------------------------------
# Semantic chunking — Stage 1a: Per-chunk section analysis
# ---------------------------------------------------------------------------

SYSTEM_ROLE_CHUNK_ANALYST = """\
You are an expert document analyst who extracts structured information from
individual sections of a document. You understand document hierarchy and context.

CRITICAL RULES:
- Use ONLY information present in the provided section content.
- Do NOT invent facts, statistics, or names.
- Be aware of the document hierarchy (parent heading, section path).
- Use the accumulated context to understand how this section fits the whole.
- Return ONLY valid JSON. No markdown. No explanation.
"""

CHUNK_ANALYSIS_PROMPT = """\
Analyze the following document section and extract structured information.

DOCUMENT TITLE: {document_title}

SECTION HIERARCHY:
{section_path}

SECTION HEADING: {heading}
SECTION LEVEL: {level}
{parent_info}

ACCUMULATED DOCUMENT CONTEXT (what has been covered so far):
{accumulated_context}

SECTION CONTENT TO ANALYZE:
{content}

Extract and return a JSON object with this EXACT structure:
{{
  "chunk_id": "{chunk_id}",
  "heading": "{heading}",
  "level": {level},
  "parent_heading": {parent_heading_json},
  "section_path": {section_path_json},
  "summary": "2-3 sentence summary of this section only",
  "key_points": ["key point from this section", "another key point"],
  "facts": ["factual statement verbatim from content", "..."],
  "statistics": ["any number/percentage/metric mentioned", "..."],
  "processes": ["any workflow or process described", "..."],
  "comparisons": ["any comparison or contrast mentioned", "..."],
  "dates": ["any date, timeline, or milestone mentioned", "..."],
  "examples": ["any example or case study mentioned", "..."],
  "relationships": ["how concepts in this section connect", "..."],
  "potential_visuals": ["suggested slide layout or visual type", "..."],
  "content_types": ["STATS", "BULLETS", "CARDS_2_COL"],
  "importance": "high|medium|low"
}}

RULES:
- content_types must be chosen from: BULLETS, STATS, CARDS_2_COL, CARDS_3_COL,
  TABLE, IMAGE_TEXT, TIMELINE, CONCLUSION, SECTION_HEADER
- importance: "high" if this section contains key facts/numbers/decisions
- Lists may be empty [] if nothing found in this section
- Use ONLY facts from the section content above

Return ONLY the JSON object. No preamble. No explanation.
"""

# ---------------------------------------------------------------------------
# Semantic chunking — Auto-structure inference for unstructured documents
# ---------------------------------------------------------------------------

SYSTEM_ROLE_STRUCTURE_INFERRER = """\
You are an expert at identifying the logical structure within unstructured documents.
Your job is to infer headings and section boundaries from plain text content.

CRITICAL RULES:
- Only create sections where content clearly changes topic.
- Be conservative — do NOT create a section for every paragraph.
- The inferred structure must closely follow the content's natural flow.
- Return ONLY valid JSON. No markdown. No explanation.
"""

AUTO_STRUCTURE_PROMPT = """\
The following document has no explicit headings or formatting.
Analyze the content and infer its logical section structure.

DOCUMENT CONTENT:
{content}

Based on the content, identify the main topics and logical sections.

Return a JSON object with this EXACT structure:
{{
  "inferred_title": "The likely title/topic of this document",
  "sections": [
    {{
      "heading": "Inferred section heading",
      "level": 1,
      "start_marker": "First 8-10 words that mark the start of this section in the text",
      "subsections": [
        {{
          "heading": "Inferred subsection heading",
          "level": 2,
          "start_marker": "First 8-10 words that mark the start of this subsection"
        }}
      ]
    }}
  ]
}}

RULES:
- Create 3-8 top-level sections maximum for a typical document
- Only create subsections if the content clearly has sub-topics
- start_marker must be EXACT words from the content (used to split the text)
- Do NOT invent section headings that don't reflect actual content
- If the document is very short (<500 chars), create only 2-3 sections

Return ONLY the JSON object. No preamble. No explanation.
"""

# ---------------------------------------------------------------------------
# Semantic chunking — Consolidation: merge N chunk analyses → ContentAnalysis
# ---------------------------------------------------------------------------

SYSTEM_ROLE_CONSOLIDATOR = """\
You are an expert at synthesizing multiple document section analyses into a
unified content analysis for presentation creation.

CRITICAL RULES:
- Preserve the document hierarchy in your synthesis.
- Do NOT invent facts not present in the section analyses.
- Identify the most presentation-worthy content across all sections.
- Return ONLY valid JSON. No markdown. No explanation.
"""

CONSOLIDATION_PROMPT = """\
You have analyzed a document section by section. Now synthesize all analyses
into a master content analysis for creating a presentation.

DOCUMENT TITLE: {document_title}

DOCUMENT STRUCTURE:
{structure_outline}

SECTION-BY-SECTION ANALYSES:
{section_analyses}

USER REQUIREMENTS:
- Target Audience: {audience}
- Presentation Style: {style}
- Requested Slides: {slide_count}
- Language: {language}
- Additional Instructions: {additional_instructions}

Based on ALL section analyses above, return a unified JSON content analysis:
{{
  "main_topic": "Primary subject of the entire document",
  "key_concepts": ["most important concept", "second concept", "..."],
  "sections": ["section 1 heading", "section 2 heading", "..."],
  "statistics": ["important metric from any section", "..."],
  "processes": ["process or workflow from any section", "..."],
  "comparisons": ["comparison from any section", "..."],
  "timelines": ["date/milestone sequence from any section", "..."],
  "conclusions": ["key conclusion from the document", "..."],
  "recommendations": ["recommendation from the document", "..."],
  "suggested_slide_count": {suggested_slides},
  "content_types_detected": ["BULLETS", "STATS", "CARDS_2_COL", "..."],
  "summary": "3-4 sentence executive summary of the entire document",
  "executive_highlights": [
    "Most impactful takeaway from the document (max 12 words)",
    "Second most important finding or outcome (max 12 words)",
    "Third key insight or result (max 12 words)"
  ],
  "agenda_topics": ["Major section topic 1", "Major section topic 2", "Major section topic 3"]
}}

RULES:
- sections must list ALL major headings from the document
- executive_highlights: 3-5 crisp one-liners, most impactful facts/outcomes. Max 12 words each.
- agenda_topics: ordered list of the major body sections that will each get a SECTION_HEADER slide.
  Must match the natural flow of the document. Minimum 2, maximum 8 topics.
- content_types_detected: choose from TITLE, EXECUTIVE_SUMMARY, AGENDA, BULLETS, CARDS_2_COL,
  CARDS_3_COL, SECTION_HEADER, IMAGE_TEXT, TABLE, TIMELINE, STATS, CONCLUSION
- suggested_slide_count must be {suggested_slides} (user requested or auto)
- summary must be grounded in the section analyses only

Return ONLY the JSON object. No preamble. No explanation.
"""


# ---------------------------------------------------------------------------
# AI-Driven Dynamic Chunking — Boundary Detection
# ---------------------------------------------------------------------------

SYSTEM_ROLE_DYNAMIC_CHUNKER = """\
You are an expert at identifying meaningful semantic boundaries within documents.
Your task is to identify where one coherent topic ends and another begins within
a list of numbered document elements (paragraphs, headings, list items, table rows).

CRITICAL RULES:
- Treat headings as strong boundary signals, but not the only ones.
- A boundary exists when the subject, argument, or context changes meaningfully.
- Do NOT create a boundary at every paragraph — only at genuine topic shifts.
- Do NOT create boundaries that produce chunks smaller than 3 elements unless unavoidable.
- Transcripts: group by discussion topic, not by individual speaker turns.
- Return boundaries using ONLY the provided element IDs. Do NOT reproduce content.
- Return ONLY valid JSON. No markdown. No explanation.
"""

DYNAMIC_CHUNK_BOUNDARY_PROMPT = """\
You are analyzing a portion of a document to identify semantic chunk boundaries.

DOCUMENT TITLE: {document_title}
WINDOW: {window_id} (elements {first_element} to {last_element})

PRIOR CONTEXT (summary of content BEFORE this window):
{prior_context}

DOCUMENT ELEMENTS IN THIS WINDOW:
{element_listing}

Each element is shown as:
  [element_id] (type) text content

Your task:
Identify the semantic chunk boundaries within this window.
A chunk is a set of consecutive elements that discuss the same coherent topic.

Return a JSON object with this EXACT structure:
{{
  "window_id": "{window_id}",
  "boundaries": [
    {{
      "chunk_id": "chunk_{chunk_id_start:03d}",
      "start_element": "element_NNN",
      "end_element": "element_MMM",
      "topic": "Brief topic label (5-10 words)",
      "boundary_reason": "Why this chunk ends here and a new topic begins",
      "confidence": 0.95
    }}
  ]
}}

RULES:
- chunk_id values must be sequential integers starting at {chunk_id_start}
  (e.g. if chunk_id_start is 3, use chunk_003, chunk_004, ...)
- start_element and end_element must be EXACT element IDs from the listing above
- The first chunk MUST start at {first_element}
- The last chunk MUST end at {last_element}
- Chunks must be contiguous and non-overlapping
- Minimum chunk size: {min_elements} elements
- confidence: 0.0 (uncertain) to 1.0 (definitive topic shift)
- boundary_reason must explain the semantic shift, not just restate the topic

Return ONLY the JSON object. No preamble. No explanation.
"""
