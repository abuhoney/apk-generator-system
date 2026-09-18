# BardomPro APK Generator

**Universal function-based APK generation system.**

Build real Android APKs from any function — calculator, notes, todo list, QR generator, weather, or your own custom function — with a clean modular architecture where every function owns its own folder, its own `config.json`, its own `strings.json`, and its own `template.html`.

---

## Architecture

```
apk-generator-system/
├── backend/                    # Flask backend (the engine)
│   ├── app.py                  # Main Flask app with all API routes
│   ├── engine/                 # Core engine
│   │   ├── config.py                       # Loads .env credentials
│   │   ├── function_registry.py            # Discovers function folders
│   │   ├── code_extractor.py               # Walks code, extracts IDs + strings
│   │   ├── config_json_processor.py        # Builds config.json (all IDs + full code)
│   │   ├── strings_json_processor.py       # Builds strings.json (all strings per ID, ordered)
│   │   ├── template_renderer.py            # Renders template.html using strings.json
│   │   ├── project_generator.py            # Generates full Android project tree per function
│   │   └── apk_builder.py                  # Builds the APK (Gradle or webapk fallback)
│   └── integrations/          # External service clients
│       ├── github_client.py                # Push to a NEW GitHub repo (never overwrites)
│       ├── render_client.py                # Trigger Render deploys
│       ├── telegram_bot.py                 # Send messages / APKs via Telegram
│       ├── firebase_client.py              # Record builds in Firebase RTDB
│       └── zip_builder.py                  # Package everything as a zip
├── functions/                 # Each function in its own folder
│   ├── calculator/            # ← example function
│   │   ├── function.json      # Function manifest (name, version, package)
│   │   ├── handler.py         # Python entry point (pure logic)
│   │   ├── template.html      # HTML template with {{ strings.by_id... }} placeholders
│   │   ├── config.json        # ← auto-built: every ID + full code
│   │   ├── strings.json       # ← auto-built: every string per ID, in order
│   │   ├── rendered.html      # ← auto-built: template rendered with strings
│   │   ├── css/style.css
│   │   └── js/app.js
│   ├── notes/
│   ├── todo_list/
│   ├── qr_generator/
│   └── weather/
├── scripts/                    # CLI scripts
│   ├── build_all_metadata.py  # Build config.json + strings.json + rendered.html for all functions
│   ├── build_apk_cli.py       # Build an APK for a single function
│   ├── package_zip.py         # Package the entire project as a zip
│   ├── push_github.py         # Push to a NEW GitHub repo
│   ├── deploy_render.py       # Trigger a Render deploy
│   └── list_functions.py      # List every function module
├── android/                    # WebView APK wrapper (the dashboard on your phone)
│   ├── app/
│   │   ├── build.gradle
│   │   └── src/main/
│   │       ├── AndroidManifest.xml
│   │       ├── java/com/bardom/generator/MainActivity.java
│   │       └── res/...
│   ├── build.gradle
│   ├── settings.gradle
│   └── gradle.properties
├── dashboard/                  # Web dashboard (served by the backend)
├── _builds/                    # Generated Android projects (gitignored)
├── _output/                    # Built APKs (gitignored)
├── .env                        # All credentials (NEVER commit)
├── render.yaml                 # Render deployment config
├── requirements.txt            # Python dependencies (Flask + gunicorn only)
├── setup.sh                    # Detect Android SDK + JDK paths
└── start.sh                    # Launch the backend
```

---

## The two key processors

### `config.json` processor

For every function folder, walks every source file (`.py`, `.js`, `.ts`, `.java`, `.kt`, `.html`, `.css`, `.json`, `.xml`, `.gradle`, `.sh`) and extracts:

* **every ID** — function names, class names, variables, XML view IDs, JSON keys, CSS selectors
* **the full code block** for each ID — from `line_start` to `line_end`, complete, no truncation
* **branching structure** — sub-functions point to their parent via `branch_of`, and the parent's `children` list points back

Output schema:

```json
{
  "function": "calculator",
  "version": "1.0.0",
  "generated_at": "...",
  "summary": { "files": 7, "ids": 42, "languages": ["python", "html", ...] },
  "files": [{ "path": "handler.py", "language": "python", "lines": 142, "ids": [...] }],
  "ids_index": { "calculate_total": { "file": "handler.py", "line_start": 12, ... } },
  "tree": { "calculate_total": { "_meta": {...}, "_code": "def calculate_total(...): ...", "children": {...} } }
}
```

### `strings.json` processor

For every function folder, extracts **every string literal** — quoted strings, XML text content, JSON values — **in the exact order they appear** in each source file, and groups them by the ID they belong to (function / class / module).

Output schema:

```json
{
  "function": "calculator",
  "summary": { "files": 7, "total_strings": 87, "ids_with_strings": 12 },
  "global_strings": [ { "text": "Calculator", "file": "handler.py", "line": 1 } ],
  "by_id": {
    "calculate_total": [
      { "text": "Total amount", "file": "handler.py", "line": 14 },
      { "text": "Invalid input", "file": "handler.py", "line": 18 }
    ]
  },
  "ordered": [ { "text": "...", "file": "...", "line": N, "id": "..." } ]
}
```

### `template.html` renderer

Each function folder ships a `template.html` with placeholders that pull from `strings.json` and `config.json`:

```html
<title>{{ config.function }} — Calculator</title>
<h1>{{ strings.global_strings[0].text }}</h1>
{{#each strings.by_id.calculate_total}}
  <li>{{ this.text }}</li>
{{/each}}
```

The renderer supports:
* `{{ a.b.c }}` dot-path lookups
* `{{ a.b[0].c }}` index lookups
* `{{#if var}}...{{/if}}` conditionals
* `{{#each list}}...{{/each}}` loops with `{{ this }}` and `{{ @index }}`

---

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. (Optional) detect Android SDK + JDK

```bash
./setup.sh
```

If the SDK is not installed, APK builds will fall back to "webapk" mode (a signed ZIP that bundles the rendered webapp). Both modes produce a downloadable `.apk` file.

### 3. Build metadata for every function

```bash
python3 scripts/build_all_metadata.py
```

This writes `config.json`, `strings.json`, and `rendered.html` into every function folder.

### 4. Build an APK for one function

```bash
python3 scripts/build_apk_cli.py calculator
```

Output:

```
✓ Built calculator → _output/calculator/Calculator.apk
  mode:  webapk
  size:  12.3 KB
  time:  0.4s
```

### 5. Run the backend

```bash
./start.sh
# or: python3 backend/app.py
```

Open `http://localhost:3000` — the dashboard shows every function, lets you build APKs, push to GitHub, deploy to Render, and send Telegram messages.

### 6. Push to GitHub (NEW repo — does NOT touch existing files)

```bash
python3 scripts/push_github.py
```

Creates `abuhoney/apk-generator-system` if it doesn't exist, then upserts every local file. Remote files that aren't in the local tree are left untouched.

### 7. Deploy to Render

```bash
python3 scripts/deploy_render.py
```

Triggers a fresh deploy of the Render service. Health check at `GET /api/health`.

### 8. Build the Android wrapper APK

```bash
cd android
./gradlew assembleRelease
# Output: android/app/build/outputs/apk/release/app-release.apk
```

This APK installs the dashboard on your phone — you can then build APKs, download them, push to GitHub, and deploy to Render — all from the device.

---

## Adding a new function

1. Create `functions/my_function/` with:
   * `function.json` — manifest
   * `handler.py` — Python logic (optional, but recommended)
   * `template.html` — HTML template with `{{ strings... }}` / `{{ config... }}` placeholders
   * `css/style.css` — styles (optional)
   * `js/app.js` — front-end logic (optional)

2. Build its metadata:

   ```bash
   python3 scripts/build_all_metadata.py --function my_function
   ```

3. Build its APK:

   ```bash
   python3 scripts/build_apk_cli.py my_function
   ```

That's it — the new function automatically appears in the dashboard, the API, and the Telegram bot.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/functions` | List all functions |
| GET | `/api/functions/<name>` | Function detail |
| POST | `/api/build-config-json` | Build `config.json` for one function |
| POST | `/api/build-strings-json` | Build `strings.json` for one function |
| POST | `/api/build-templates` | Render `template.html` for one function |
| POST | `/api/build-all-metadata` | Build everything for all functions |
| POST | `/api/build-apk` | Build an APK |
| GET | `/api/apks` | List built APKs |
| GET | `/download/<fn>/<file>` | Download a built APK |
| POST | `/api/github/push` | Push to GitHub |
| POST | `/api/render/deploy` | Deploy to Render |
| POST | `/api/telegram/notify` | Send Telegram message |
| GET | `/api/render/health` | Render service status |
| GET | `/api/firebase/builds` | Builds recorded in Firebase |

---

## License

MIT
