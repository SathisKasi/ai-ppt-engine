# 🎯 AI-Powered Document/Prompt to Editable PowerPoint Generator

Transform documents and ideas into professional, fully editable `.pptx` presentations using Groq LLM + Streamlit.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-red)
![Groq](https://img.shields.io/badge/Groq-LLM-orange)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

- **Dual Input Modes** — Upload `.txt`, `.docx`, or `.pdf` documents OR enter a free-form prompt
- **Two-Stage LLM Pipeline** — Content analysis → Presentation planning → Slide generation
- **11 Professional Layouts** — TITLE, TITLE_AND_CONTENT, TWO_COLUMN, SECTION_HEADER, IMAGE_TEXT, COMPARISON, TIMELINE, PROCESS, ARCHITECTURE, STATISTICS, CONCLUSION
- **Semantic Layout Selection** — LLM automatically picks the best layout for each slide's content type
- **Fully Editable Output** — All text, shapes, and tables remain editable in Microsoft PowerPoint
- **Pydantic Validation** — Structured JSON validation with retry logic
- **Anti-Hallucination** — Source-grounded content generation
- **Premium Dark UI** — Professional Streamlit interface with glassmorphism design
- **One-Click Download** — Download the `.pptx` directly from the browser

---

## 🚀 Quick Start

### 1. Clone / Download

```bash
git clone <repo-url> ai-ppt-generator
cd ai-ppt-generator
```

### 2. Create a Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

For Groq, edit `.env` and add your Groq API key:

```env
GROQ_API_KEY=gsk_your_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

Get your free API key at: [https://console.groq.com/keys](https://console.groq.com/keys)

To use IBM watsonx.ai instead, set these values in `.env`:

```env
LLM_PROVIDER=watsonx
WATSONX_API_KEY=your_ibm_cloud_api_key
WATSONX_PROJECT_ID=your_watsonx_project_id
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL=ibm/granite-3-8b-instruct
```

The application obtains a short-lived IAM access token from the IBM Cloud API key and uses it to call watsonx.ai. Credentials are read only from environment variables.

### 5. Generate the Presentation Template

The template is auto-generated on first run, but you can also generate it manually:

```bash
python templates/create_template.py
```

### 6. Run the Application

```bash
streamlit run app.py
```

The app will open at [http://localhost:8501](http://localhost:8501)

## IBM watsonx.ai Deployment

The application can run in IBM Cloud Code Engine as a container and call watsonx.ai for model inference. The repository includes a `Dockerfile` configured for Code Engine's port `8080`.

### 1. Create IBM Cloud resources

1. Create an IBM Cloud account and create or open a watsonx.ai project.
2. From **Manage > Access (IAM) > API keys**, create an IBM Cloud API key.
3. Copy the watsonx project ID from the project details page.
4. Confirm the selected watsonx model is available in your chosen region. Set `WATSONX_URL` to that region's watsonx URL.

### 2. Push the image to IBM Container Registry

Install the IBM Cloud CLI and the Code Engine plugin, then sign in:

```bash
ibmcloud login
ibmcloud plugin install container-registry
ibmcloud plugin install code-engine
ibmcloud cr login
```

Build and push the image from the project root. Replace the placeholders with your IBM Cloud values:

```bash
ibmcloud cr namespace-add YOUR_NAMESPACE
docker build -t us.icr.io/YOUR_NAMESPACE/ai-presentation-engine:1.0 .
docker push us.icr.io/YOUR_NAMESPACE/ai-presentation-engine:1.0
```

### 3. Deploy to Code Engine

```bash
ibmcloud ce project create --name ai-presentation-project
ibmcloud ce project select --name ai-presentation-project

ibmcloud ce secret create --name watsonx-secrets \
  --from-literal WATSONX_API_KEY=YOUR_IBM_CLOUD_API_KEY \
  --from-literal WATSONX_PROJECT_ID=YOUR_WATSONX_PROJECT_ID

ibmcloud ce app create --name ai-presentation-engine \
  --image us.icr.io/YOUR_NAMESPACE/ai-presentation-engine:1.0 \
  --port 8080 \
  --min-scale 1 \
  --max-scale 2 \
  --env LLM_PROVIDER=watsonx \
  --env WATSONX_URL=https://us-south.ml.cloud.ibm.com \
  --env WATSONX_MODEL=ibm/granite-3-8b-instruct \
  --env-from-secret watsonx-secrets
```

Get the public application URL:

```bash
ibmcloud ce app get --name ai-presentation-engine
```

Open the displayed URL in a browser. Code Engine keeps the API credentials in a secret; do not commit `.env` or place keys in the Dockerfile.

### Groq and watsonx switching

The provider is selected without code changes:

```env
LLM_PROVIDER=groq
```

or:

```env
LLM_PROVIDER=watsonx
```

The presentation analysis, JSON retry logic, document parsing, and PowerPoint generation are shared by both providers.

---

## 📖 Usage

1. **Enter your Groq API key** in the left sidebar
2. **Choose your input mode:**
   - **Upload Document** — `.txt`, `.docx`, or `.pdf`
   - **Enter Prompt** — Type a topic or paste content directly
3. **Configure your presentation:**
   - Number of slides (3–30 or Automatic)
   - Target audience (General / Business / Technical / Executive)
   - Presentation style (Professional / Executive / Educational / Technical)
   - Language
   - Additional instructions
4. **Click Generate** — Watch the progress in real time
5. **Review the preview** — See all slide titles and layout types
6. **Download** your `.pptx` file

---

## 🏗️ Project Structure

```
ai_ppt_generator/
├── app.py                        # Streamlit entry point
├── config.py                     # App-wide configuration
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment template
├── README.md                     # This file
│
├── core/
│   ├── document_parser.py        # .txt/.docx/.pdf text extraction
│   ├── content_analyzer.py       # Stage-1 LLM: content analysis
│   ├── presentation_planner.py   # Stage-2 LLM: slide planning
│   ├── slide_generator.py        # Stage-3: content refinement
│   ├── pptx_builder.py           # python-pptx assembly engine
│   ├── layout_manager.py         # Layout registry + template loader
│   └── validator.py              # Quality validation
│
├── llm/
│   ├── groq_client.py            # Groq API wrapper + retry logic
│   ├── prompts.py                # All LLM prompt templates
│   └── schemas.py                # Pydantic models
│
├── templates/
│   ├── layout_metadata.json      # Layout descriptions and mappings
│   ├── create_template.py        # Template generator script
│   └── presentation_template.pptx  # Auto-generated on first run
│
├── utils/
│   ├── file_utils.py             # File validation and temp management
│   ├── text_utils.py             # Text manipulation helpers
│   └── logging_utils.py          # Structured logging
│
└── output/                       # Generated .pptx files (ephemeral)
```

---

## 🎨 Layout Types

| Layout ID | Use Case |
|-----------|----------|
| `TITLE` | Opening title slide |
| `TITLE_AND_CONTENT` | General information with bullets |
| `TWO_COLUMN` | Side-by-side content |
| `SECTION_HEADER` | Chapter / section dividers |
| `IMAGE_TEXT` | Visual placeholder + description |
| `COMPARISON` | A vs B comparisons |
| `TIMELINE` | Chronological milestones / roadmaps |
| `PROCESS` | Step-by-step workflows |
| `ARCHITECTURE` | System / technology layers |
| `STATISTICS` | KPIs and numerical highlights |
| `CONCLUSION` | Summary + call to action |

---

## 🔧 Configuration

All settings can be controlled via environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `groq` | LLM provider: `groq` or `watsonx` |
| `GROQ_API_KEY` | — | Required when using Groq |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | LLM model to use |
| `WATSONX_API_KEY` | — | Required when using watsonx.ai |
| `WATSONX_PROJECT_ID` | — | watsonx.ai project ID |
| `WATSONX_URL` | `https://us-south.ml.cloud.ibm.com` | watsonx.ai regional URL |
| `WATSONX_MODEL` | `ibm/granite-3-8b-instruct` | watsonx.ai model ID |
| `GROQ_MAX_TOKENS_PLAN` | `4096` | Max tokens for planning stage |
| `GROQ_TEMPERATURE` | `0.3` | LLM temperature (0=deterministic) |
| `LLM_MAX_RETRIES` | `3` | JSON parse retry attempts |
| `MAX_UPLOAD_SIZE_MB` | `20` | Upload file size limit |
| `MAX_SOURCE_TEXT_CHARS` | `12000` | Source text truncation limit |

---

## 🛡️ Security

- API keys are **never** stored, logged, or hardcoded
- Uploaded files are processed in-memory or via temp files (auto-deleted)
- File types are validated before processing
- Upload size limits prevent abuse

---

## 🔌 Supported Document Formats

| Format | Library | Notes |
|--------|---------|-------|
| `.txt` | Built-in + chardet | Auto-detects encoding |
| `.docx` | python-docx | Includes tables |
| `.pdf` | PyMuPDF (primary) | Falls back to pdfplumber |

---

## 🤖 LLM Pipeline

```
Source Content
    │
    ▼
Stage 1: Content Analysis
  ├─ Extract main topic
  ├─ Identify key concepts, statistics, processes
  ├─ Detect content types (PROCESS, TIMELINE, etc.)
  └─ Suggest slide count
    │
    ▼
Stage 2: Presentation Planning
  ├─ Generate slide-by-slide plan (JSON)
  ├─ Select appropriate layout per slide
  ├─ Write concise slide content
  └─ Pydantic validation (with JSON retry)
    │
    ▼
Stage 3: Content Refinement (selective)
  └─ Refine over-long bullets and paragraphs
    │
    ▼
PowerPoint Assembly
  ├─ Clone template layout slide
  ├─ Populate text boxes with content
  ├─ Preserve colors, fonts, shapes
  └─ Generate editable .pptx
```

---

## 🐛 Troubleshooting

### "Authentication failed"
- Check your Groq API key at [console.groq.com](https://console.groq.com)
- Make sure the key starts with `gsk_`

### "Could not extract text from PDF"
- The PDF may be scanned/image-based (no text layer)
- Try converting to `.txt` or `.docx` first

### "JSON parse failed"
- The app automatically retries up to 3 times
- Try a simpler prompt or reduce the slide count
- Try a different model (mixtral-8x7b-32768 may work better for some inputs)

### Template not found
```bash
python templates/create_template.py
```

---

## 📦 Dependencies

```
streamlit>=1.35.0
groq>=0.9.0
python-pptx>=1.0.0
pydantic>=2.7.0
python-dotenv>=1.0.0
python-docx>=1.1.0
PyMuPDF>=1.24.0
pdfplumber>=0.11.0
Pillow>=10.3.0
lxml>=5.2.0
chardet>=5.2.0
```

---

## 🔮 Future Roadmap

- [ ] Image generation for visual slides
- [ ] Web search / research integration
- [ ] Charts and graphs (Matplotlib/Plotly)
- [ ] Excel/CSV data input
- [ ] Multiple theme options
- [ ] Company branding and logo insertion
- [ ] Speaker notes generation
- [ ] OpenAI / Anthropic / Gemini provider support
- [ ] Chat-based slide editing
- [ ] Slide-by-slide regeneration
- [ ] Export as PDF

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
