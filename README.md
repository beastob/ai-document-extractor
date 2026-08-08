# 🇦🇺 Bank Statement PDF Extractor & ATO Tax Categorizer

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.30+-ff4b4b.svg)](https://streamlit.io/)
[![IBM Docling](https://img.shields.io/badge/IBM--Docling-2.0+-4a154b.svg)](https://github.com/DS4SD/docling)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A powerful, **100% offline & private** web application built with Streamlit for extracting transaction tables from bank statement PDFs, normalizing data structures, and automatically categorizing expenses for **Australian Tax Office (ATO)** tax returns.

Designed to run seamlessly on local workstations, Raspberry Pi (ARM64), and home server/NAS hardware (such as Synology DS920+ with Intel iGPU pass-through).

---

## 🌟 Key Features

* **Multi-Engine PDF Table Extraction Orchestrator**:
  * 🔍 **IBM Docling**: AI layout parsing & TableFormer transformer model for scanned/complex PDFs.
  * 📄 **pdfplumber**: Lightning-fast digital vector PDF extraction (< 0.5 seconds per page).
  * 🤖 **LLM Direct AI**: Direct extraction using local Ollama models (`qwen2.5:3b`, `llama3.2`).
* **ATO Tax Categorization Engine**:
  * **Offline AU Merchant Rule Engine**: Instant matching against thousands of Australian merchants (Coles, Woolworths, Bunnings, Qantas, ATO, Officeworks, Xero, etc.).
  * **Ollama AI Classifier**: Deep semantic expense classification into official ATO tax return categories (D1 Work-Related Car, D5 Work-Related Other, D7 Interest, Rental Expenses, etc.).
* **Dynamic Host Architecture Support**:
  * Automatic runtime detection (`platform.machine()`) that configures CPU threading and OpenBLAS core types (`ARMV8`) on ARM64 (Raspberry Pi 3/4/5) to prevent `SIGILL` traps while maximizing multi-core performance.
* **Interactive Statement & Tax Editor**:
  * In-browser data editor to review, edit descriptions, adjust ATO categories, update deductibility status, and add custom tax notes.
* **Batch Export Suite**:
  * Export individual statement workbooks, multi-sheet combined workbooks (`.xlsx`), merged master tax summaries, or bulk `.zip` archives.

---

## 🏗️ System Architecture

```
                               ┌──────────────────────────────────────────────┐
                               │             Uploaded PDF Files               │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │  Extraction Strategy Orchestration Engine   │
                               │             (src/extractor.py)               │
                               └──────┬───────────────┼───────────────┬───────┘
                                      │               │               │
                     ┌────────────────┘               │               └────────────────┐
                     ▼                                ▼                                ▼
       ┌───────────────────────────┐    ┌───────────────────────────┐    ┌───────────────────────────┐
       │     pdfplumber Engine     │    │     IBM Docling Engine    │    │      Ollama LLM Engine    │
       │  Digital Vector PDFs      │    │  Scanned / Complex PDFs   │    │    Direct AI Extraction   │
       │  (< 0.5s / page)          │    │  (TableFormer AI Vision)  │    │    (Local LLM Server)     │
       └─────────────┬─────────────┘    └─────────────┬─────────────┘    └─────────────┬─────────────┘
                     │                                │                                │
                     └──────────────────┐             │             ┌──────────────────┘
                                        ▼             ▼             ▼
                               ┌──────────────────────────────────────────────┐
                               │          DataFrame Normalizer                │
                               │              (src/parser.py)                 │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │         ATO Tax Categorization Engine        │
                               │           (src/llm_processor.py)             │
                               │     [AU Rule Matcher | Ollama LLM]           │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │        Interactive Streamlit UI & Editor     │
                               │                   (app.py)                   │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │       Excel Exporter & Batch Zip Suite       │
                               │           (src/excel_exporter.py)            │
                               └──────────────────────────────────────────────┘
```

---

## 🚀 Quick Start (Local Workstation)

### Prerequisites
* Python 3.11 or higher
* (Optional) [Ollama](https://ollama.com/) running locally if using LLM features.

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/beastob/ai-document-extractor.git
   cd ai-document-extractor
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   # On Linux/macOS:
   source venv/bin/activate
   # On Windows PowerShell:
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Streamlit application**:
   ```bash
   streamlit run app.py
   ```
   Open your browser at `http://localhost:8501`.

---

## 🐳 Docker Deployment & Multi-Platform Builds

### 1. Single-Architecture Build & Run
To build locally for your current host architecture:

```bash
docker build -t ai-document-extractor:latest .
docker run -d -p 8501:8501 --name ai-document-extractor ai-document-extractor:latest
```

### 2. Multi-Platform Build (`linux/amd64` & `linux/arm64`)
To build a multi-platform image manifest supporting both Intel/AMD x86_64 servers and ARM64 single-board computers (Raspberry Pi), use Docker `buildx`:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t dockerhub.beastob.com/ai-document-extractor:latest \
  --push .
```

#### How Multi-Platform Deployment Works:
* **x86_64 Servers**: Docker automatically pulls the `linux/amd64` slice.
* **Raspberry Pi (ARM64)**: Docker automatically pulls the `linux/arm64` slice. The application dynamically initializes OpenBLAS and multi-threaded CPU settings (`OMP_NUM_THREADS`) at runtime.

---

## 🖥️ Deploying on Synology NAS (Intel iGPU Hardware Acceleration)

Synology NAS models featuring Intel processors with integrated graphics (e.g. **Synology DS920+** with **Intel Celeron J4125** and **Intel UHD Graphics 600**) can accelerate IBM Docling and ONNX Runtime vision models using Intel **OpenCL / OpenVINO** hardware pass-through.

### 1. Docker Compose Configuration
To pass the Intel GPU hardware render node (`/dev/dri`) into the Docker container, configure your `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ai-document-extractor:
    image: dockerhub.beastob.com/ai-document-extractor:latest
    container_name: ai-document-extractor
    ports:
      - "8501:8501"
    devices:
      - /dev/dri:/dev/dri  # Pass-through Intel UHD Graphics iGPU (/dev/dri/renderD128)
    environment:
      - OLLAMA_HOST=http://host.docker.internal:11434
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
```

### 2. Start the Service on Synology NAS
Deploy via Synology Container Manager (or SSH terminal):

```bash
docker compose up -d
```

#### Hardware Acceleration Notes:
* **Docling Auto-Detection**: When `/dev/dri` is mounted, `AcceleratorDevice.AUTO` in `src/extractor.py` detects the Intel graphics hardware (`XPU` / OpenVINO) and offloads tensor matrix multiplication to the 12 execution units on the Intel UHD 600 GPU.
* **x86 CPU Performance**: The 4-core Celeron J4125 CPU executes vector math significantly faster than ARM micro-architectures.

---

## 🥧 Deploying on Raspberry Pi 4 (ARM64 Optimization Guide)

### Hardware Limitations & Optimizations
* **No CUDA GPU**: The Raspberry Pi 4 Broadcom VideoCore VI GPU does not support CUDA or PyTorch compute backends.
* **4-Core CPU Acceleration**: The application automatically sets `OMP_NUM_THREADS=4` on ARM64, forcing PyTorch and ONNX Runtime to utilize all 4 Cortex-A72 cores in parallel.

### Recommended Usage on Raspberry Pi:
1. **Digital Bank Statements**: Select **`📄 pdfplumber (Fast Digital Vector PDFs)`** in the UI sidebar. Vector extraction executes in **< 0.5s per page**.
2. **Network LLM Offloading**: Point `OLLAMA_HOST` in `docker-compose.yml` to an Ollama instance running on your workstation GPU (`http://<DESKTOP_IP>:11434`), using the Pi purely as a low-power frontend.

---

## 🧪 Testing

Run the automated test suite using `pytest`:

```bash
python -m pytest
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
