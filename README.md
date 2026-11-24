# California University, America — Smart Campus Navigator (Python & Streamlit)

Complete standalone Python + Streamlit implementation of the Smart Campus Navigator featuring multi-floor Dijkstra indoor corridor routing, visual step-by-step blueprint navigation, emergency fire evacuation routing, Wi-Fi network zone monitoring, outdoor OpenStreetMap + BLE beacon calibration, teachers & availability directory, printable room QR plaques, and a local SQLite-backed Admin Portal.

## Prerequisites
- **Python 3.10+** installed ([python.org](https://www.python.org/downloads/))
- **VS Code** with the **Python** extension (`ms-python.python`)

## Setup & Run in VS Code

1. **Extract the ZIP** into a folder (for example `california_university_streamlit`).
2. **Open the folder in VS Code**: `File -> Open Folder... -> california_university_streamlit`.
3. **Open the VS Code Integrated Terminal** (`Ctrl + ~` or `Terminal -> New Terminal`).
4. **Create and activate a virtual environment**:
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
5. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
6. **Run the Streamlit app**:
   ```bash
   streamlit run app.py
   ```
   Or press **`F5`** in VS Code using the pre-configured `.vscode/launch.json` debugger profile.

The app opens automatically in your browser at **http://localhost:8501**.

## Admin Portal Demo Credentials
- **Email:** `admin@californiauniversity.edu`
- **Password:** `Admin@1234`
(Or register a new local administrator account directly inside the Admin Portal tab.)

## Project Structure
- `app.py` — Streamlit multi-tab application
- `campus_app/database.py` — Auto-seeded SQLite persistence (`data/campus.db`)
- `campus_app/pathfinding.py` — State-space Dijkstra indoor, cross-floor, and emergency routing
- `campus_app/map_renderer.py` — Floor-plan route, pin, graph, and Wi-Fi overlay renderer
- `campus_app/qr_tools.py` — Printable room QR plaque PNG generator & scanner matcher
- `campus_app/i18n.py` — English (`en`) & Kannada (`kn`) translations
- `data/campus_seed.json` — Seeded rooms, nodes, edges, exits, teachers, and Wi-Fi zones
- `assets/images/` — Floor plan and step-by-step corridor blueprint images
