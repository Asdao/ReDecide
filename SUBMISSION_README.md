# RE:DECIDE — Garena AI Build Challenge 2026

> **"Don't replay the match. Replay the decision."**

Welcome to the **Team Pandamonium** submission for the **Garena AI Build Challenge 2026**.

---

## 🔗 Quick Access Links

| Resource | Link / Details |
|---|---|
| 🌐 **Live Deployed Web App** | [https://g-hackathon.vercel.app](https://g-hackathon.vercel.app) |
| 💻 **GitHub Repository** | [https://github.com/Asdao/GHackathon](https://github.com/Asdao/GHackathon)<br>*(Private repository — `garena-ai-build-challenge` invited as collaborator)* |
| 📁 **Google Drive Submission** | [Google Drive Folder Link](https://drive.google.com/drive/folders/1Eima82TLMptejoeU0MlVPEEJhM6KafMg?usp=sharing) |
| 📹 **Demo Video** | `Team_Pandamonium_Redecide-demo-voiced-subtitled.mp4` *(4 min 35 sec)* |
| 📄 **Slide Deck Proposal** | `Team Pandamonium_Redecide_Slide_Deck.pdf` *(10 slides)* |

---

## 🗺️ Repository Structure & Navigation Guide

This repository is structured as a full-stack monorepo containing our CS2 replay parsing engine, AI tactical coaching pipeline, and interactive web dashboard.

```text
.
├── frontend/             # Next.js 14, React, TypeScript, Tailwind CSS
│   ├── src/app/          # Application routes, pages, and Vercel Blob / API proxy routes
│   ├── src/components/   # Interactive radar, replay timeline, moment cards, intent composer UI
│   └── public/replays/   # Pre-processed sample replay datasets
│
├── backend/              # FastAPI Python server & AI Coaching Engine
│   ├── app/              # REST API endpoints, uploaded demo handlers, and analysis controllers
│   ├── app/coach/        # Intent coaching engine & bounded evidence LLM prompt generators
│   └── app/replay/       # Telemetry parser, spatial calculations, and win-probability modeling
│
├── data/                 # Sample CS2 telemetry replays (.dem & parquet metadata)
├── docs/                 # Product documentation, API schemas, and architecture plans
├── scripts/              # Automated environment setup, dev launchers, and test runners
├── vercel.json           # Vercel monorepo deployment & serverless routing config
└── README.md             # Core developer setup & technical documentation
```

### Key Components

1. **Replay Telemetry Parser (`backend/app/replay`)**:
   Parses Counter-Strike 2 `.dem` files into structured player positions, crosshair locks, damage events, utility usage, and post-contact decision moments.
2. **Win Probability & Statistical Model**:
   Uses `Awpy` & `LightGBM` models to compute real-time win-chance fluctuations before and after critical decision points.
3. **AI Intent Coaching Engine (`backend/app/coach`)**:
   Combines factual telemetry evidence with LLMs (e.g. DeepSeek / Gemini) to explain player decision moments, map intent statements to tactical goals, and provide actionable advice without hallucinating replay facts.
4. **Interactive Dashboard (`frontend/`)**:
   Provides dynamic 2D radar playback, interactive timelines, win-probability graphs, and an intent follow-up interface.

---

## 🛠️ Local Setup & Quick Start Guide

### Prerequisites
- **Python 3.10+** (with `uv` or `pip`)
- **Node.js 18+** (with `npm` or `pnpm`)

---

### Step 1: Clone Repository & Configure Environment

```bash
# Clone private repository (or unzip Team_Pandamonium_Redecide-main.zip)
git clone git@github.com:Asdao/GHackathon.git
cd GHackathon

# Copy root environment configuration
cp .env.example .env

# Configure frontend environment file
cat <<EOF > frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_REPLAY_UPLOAD_MODE=direct
EOF
```

*(Optional: Add your `DEEPSEEK_API_KEY` or `GEMINI_API_KEY` to `.env` if testing live LLM coaching generation).*

---

### Step 2: Start Development Servers

#### Option A: Automatic Launcher (PowerShell / macOS)

* **macOS / Linux**:
  ```bash
  # Start Backend API
  uvicorn backend.main:app --reload --port 8000 &
  
  # Start Frontend UI
  cd frontend && npm run dev
  ```

* **Windows (PowerShell)**:
  ```powershell
  .\scripts\start-dev.ps1
  ```

---

### Step 3: Access the Prototype

Once started, open your browser to:
- 🎨 **Web Interface**: `http://localhost:3000`
- ⚙️ **Backend OpenAPI Docs**: `http://127.0.0.1:8000/docs`

---

## 🛡️ Security & Disclosures

- **Security Compliance**: No passwords, private credentials, or live production API keys are included in this source code or repository history.
- **Third-Party Disclosures**:
  - **Frontend**: Next.js, React, TypeScript, Tailwind CSS, Zod, Lucide Icons.
  - **Backend**: FastAPI, Pydantic, Uvicorn, Awpy, LightGBM, Pandas, NumPy.
  - **AI Integration**: OpenAI / DeepSeek / Gemini API adapters for bounded intent explanation.

---

*Submitted by **Team Pandamonium** for Garena AI Build Challenge 2026.*
