# SKILLS.md — BardomPro Universal APK Generator

**Version:** 6.0.0
**Status:** Production Specification
**Language:** English (technical), with Arabic context preserved where it appears in source
**Last Updated:** 2026-09-18

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Source Files Inventory](#2-source-files-inventory)
3. [Features Extracted from Each Source](#3-features-extracted-from-each-source)
4. [Target Project Architecture](#4-target-project-architecture)
5. [The Universal APK Builder](#5-the-universal-apk-builder)
6. [The Main APK (Self-Contained, Offline-First)](#6-the-main-apk-self-contained-offline-first)
7. [Security & Anti-Decompilation](#7-security--anti-decompilation)
8. [Function-Based Modular System](#8-function-based-modular-system)
9. [config.json / strings.json / template.html Processors](#9-configjson--stringsjson--templatehtml-processors)
10. [Backend (Render) Role](#10-backend-render-role)
11. [GitHub Integration](#11-github-integration)
12. [Telegram Bot Integration](#12-telegram-bot-integration)
13. [Firebase Integration](#13-firebase-integration)
14. [Build Pipeline](#14-build-pipeline)
15. [Auto-Update Mechanism](#15-auto-update-mechanism)
16. [Self-Test Suite](#16-self-test-suite)
17. [Deployment Plan](#17-deployment-plan)
18. [File Tree (Final Project)](#18-file-tree-final-project)
19. [Glossary](#19-glossary)

---

## 1. Executive Summary

This document specifies a **Universal APK Generator** — a single project that can build unlimited, real, installable Android APKs of any function, any content, any size, and any permission set, directly from the main APK's own UI without recompiling the main APK itself.

The system merges four source artifacts into one coherent platform:

| Source | Role |
|--------|------|
| `Universal_App_Generator.zip` | 100-template engine + aapt2/javac/d8/apksigner pipeline reference |
| `sketchware_app_generator (17).html` + `waw.html` | The Sketchware Pro Generator UI — extracts every ID, string, and function from any HTML, generates Kotlin/Java/Gradle, builds full APK, pushes to GitHub, triggers Render |
| `sketchware_app_generator (17)_modular_project_v3_1.zip` | The **modular output** of running `waw.html` on the Sketchware HTML — 301 IDs, 2,572 strings, 372 JS functions, 22 modules, 21 functional groups — this is the gold-standard structure we replicate |
| `bardom-platform.zip` (v17-34) | A complete production Android platform with: SecurityShield, LibraryInstallerWorker (downloads deps from GitHub at runtime), FunctionsEngine (dynamic functions from Firebase), encrypted LocalStorage, Telegram bot, FCM, Render backend, GitHub Actions CI/CD |

### Core Principles

1. **Unlimited APKs** — any function, any content, any size, any permissions
2. **Offline-first main APK** — does not depend on backend continuously; only fetches updates when available
3. **Auto-update without rebuild** — new functions, new templates, new strings are downloaded from GitHub and injected at runtime; the main APK never needs recompilation
4. **Anti-decompilation** — ProGuard/R8 obfuscation, signature verification, debugger detection, emulator detection, encrypted assets so Apktool/Jadx cannot reach `.env`, database, user data, or per-user permissions
5. **Progress bar on first install** — the main APK shows a progress bar while it downloads the full project payload from GitHub, encrypts it, and stores it locally
6. **Function-based modularity** — every function owns its folder, its `config.json`, its `strings.json`, its `template.html`, its `handler.py`, its CSS/JS — exactly as proven in the v3.1 modular output

---

## 2. Source Files Inventory

### 2.1 `Universal_App_Generator.zip` (9.0 MB, 8,603 files)

- **Engine modules**: `engine/config.py`, `engine/prompt_parser.py`, `engine/project_generator.py`, `engine/apk_builder.py`, `engine/code_generator.py`, `engine/self_test.py`
- **Integrations**: `integrations/telegram_bot.py`, `integrations/github_client.py`, `integrations/render_client.py`, `integrations/ai_client.py`, `integrations/firebase_client.py`
- **Templates**: 100 ready-to-build template apps (`template_001_calculator.json` … `template_100_tax_estimator.json`)
- **CLI + Web UI**: `cli.py`, `web_ui.py` (Flask dashboard)
- **Build scripts**: `build_apk.sh` (portable shell-only build), `setup.sh` (auto-detects Android SDK + JDK)
- **Image-to-APK pipeline**: `Image_to_apk/` (base64 → binary → real PNG → APK)
- **Self-test output**: full build artifacts for all 100 templates

### 2.2 `sketchware_app_generator (17).html` (1.61 MB) + `waw.html` (160 KB)

- `waw.html` is the **Sketchware Pro Generator v4.0.3** — a 100% client-side HTML tool that:
  - Accepts a Sketchware HTML file via drag-drop
  - Runs 13 self-tests
  - Extracts every ID, every string, every function (byte-for-byte, no truncation)
  - Generates real `.kt` / `.java` / `.gradle` files
  - Builds a complete Android project
  - Pushes to GitHub, triggers Render deploys, notifies Telegram
- `sketchware_app_generator (17).html` is the input Sketchware generator (17.4k lines) — a full app-build studio with tabs: Import, Extraction, Kotlin Output, Gradle, Resources, Manifest, Preview, Providers, Deploy, Build APK, Console

### 2.3 `sketchware_app_generator (17)_modular_project_v3_1.zip` (9.2 MB, 754 files)

This is the **gold-standard modular output** produced by running `waw.html` on the Sketchware HTML. It proves the structure we replicate:

| Folder | Purpose | Count |
|--------|---------|-------|
| `config/config.json` | Every element ID + tag + group | 1.2 MB |
| `data/config.json` | Duplicate of config | 1.2 MB |
| `strings/strings.json` | Every string, ordered | — |
| `ids/<group>/` | One `.html` per element ID | **301 IDs** across 21 groups |
| `js/modules/<module>/` | One file per function | **372 JS functions** in 22 modules |
| `js/globals/` | Template-string globals | 3 |
| `html/head.html`, `html/body.html` | Split HTML parts | 1.6 MB body |
| `css/styles.css` | All styles | 66 KB |
| `meta/diagnostics.json` | Per-function sizes, orphans, stats | — |
| `meta/skipped-placeholder-ids.json` | Filtered IDs | 12 skipped |
| `original/source.html` | Original file preserved | 1.6 MB |
| `assets/_index.json` | Static assets manifest | — |

**Statistics**: 301 valid IDs, 12 skipped placeholders, 21 functional groups, 2,572 strings, 372 JS functions, 3 template-string globals, 22 modules, largest function 14 KB, average 1.36 KB.

### 2.4 `bardom-platform.zip` (v17-34, 197 KB, 93 files)

A complete production Android platform — the reference for security, runtime library installation, dynamic functions, and CI/CD:

- **Android app** (`app/`): 22 Java files across 10 packages
  - `MainActivity.java` (21.8 KB) — WebView host with extended JS bridge
  - `SecurityShield.java` — ProGuard/R8 + signature verification + debugger/emulator/root detection
  - `LibraryInstallerWorker.java` — downloads required libraries from GitHub at first online run
  - `FunctionsEngine.java` — dynamic functions from Firebase (add_points, remove_points, purchase, reward_link, message, custom)
  - `LocalStorage.java` — encrypted SharedPreferences (device ID, session, libs cache, inbox, points, FCM token)
  - `BardomBuildManager.java` — APK build manager
  - `AgentOrchestrator.java` — background agent task orchestration
  - `Bot/TelegramBotService.java` (14 KB) — long-polling Telegram bot in foreground service
  - `net/FirebaseRestClient.java`, `net/TelegramBotClient.java` — REST clients (no SDK dependency)
  - `points/PointsManager.java` — points system with min/max
  - `render/GitHubReleaseUploader.java`, `render/RenderApkUploader.java`
  - `fcm/BardomMessagingService.java` — FCM push notifications
- **Engine HTML** (`app/src/main/assets/engine/`):
  - `engine.html` (388 KB) — the full engine UI loaded in WebView
  - `index.html` (26 KB) — entry point
  - `admin.html` (20 KB) — admin panel
- **Bot** (`bot.py`, 44.8 KB): Pyrogram bot with 11 commands (start, link, points, functions, invite, inbox, buy, Bardom, cancel, add_points, newfunc, announce)
- **Render backend** (`render-backend/src/server.js`, 7.8 KB): Express server that triggers GitHub Actions builds, receives webhooks, talks to Firebase + Telegram
- **GitHub Actions** (`.github/workflows/`):
  - `build-platform.yml` — builds the platform APK with JDK 17 + Android SDK 34 + Gradle 8.5
  - `zip-build.yml` — builds an APK from an uploaded ZIP (downloads from Firebase, unzips, builds, uploads to Releases)
- **ProGuard rules** (`app/proguard-rules.pro`): obfuscation, Log stripping, Firebase/Gson/OkHttp keep rules, JS bridge protection
- **Build scripts**: `build.sh` (Gradle + raw aapt2/d8/apksigner modes), `scripts/install-gradle.sh`
- **Config**: `secrets.properties` pattern (15 BuildConfig fields injected at build time)

---

## 3. Features Extracted from Each Source

### 3.1 From `Universal_App_Generator.zip`

| Feature | How we use it |
|---------|---------------|
| 100-template library | Reference for diverse app types (calculator, notes, QR, games, IoT, finance, health, etc.) |
| `engine/apk_builder.py` pipeline | aapt2 compile → link → javac → d8 → zipalign → apksigner |
| `engine/prompt_parser.py` | Natural-language prompt → feature manifest |
| `engine/code_generator.py` | AI-powered Activity code generation (Kimi K2 via OpenRouter) |
| `engine/self_test.py` | End-to-end build verification for every template |
| `Image_to_apk/` pipeline | base64 → binary → real PNG → APK asset |
| Flask `web_ui.py` | Dashboard with app-type selector (JSON/HTML/ZIP/Music/Photos/Video/Image to APK) |

### 3.2 From `waw.html` + `sketchware_app_generator (17).html`

| Feature | How we use it |
|---------|---------------|
| 13 self-tests | Adopted as the verification suite for the modular extractor |
| Byte-for-byte ID extraction | Every ID extracted with full code block (start → end), no truncation |
| String extraction (ordered) | Every string per ID, in source order, file by file |
| Branch-aware extraction | Sub-functions point to parent via `branch_of`; parent's `children` lists back |
| Kotlin/Java/Gradle generation | Real `.kt` / `.java` / `.gradle` files from extracted structure |
| Provider system | GitHub, Render, Telegram, Firebase providers — all optional, ZIP works without tokens |
| Deploy tab | Push to GitHub + trigger Render + notify Telegram in one flow |

### 3.3 From `sketchware_app_generator (17)_modular_project_v3_1.zip`

This is the **structural blueprint** we replicate exactly:

| Structural element | Our equivalent |
|---------------------|-----------------|
| `config/config.json` (1.2 MB) | `functions/<name>/config.json` — every ID + tag + group |
| `strings/strings.json` | `functions/<name>/strings.json` — every string, ordered |
| `ids/<group>/<id>.html` (301 files) | `functions/<name>/ids/<group>/<id>.html` — one file per ID |
| `js/modules/<module>/<fn>.js` (372 files) | `functions/<name>/js/modules/<module>/<fn>.js` |
| `js/globals/` | `functions/<name>/js/globals/` |
| `html/head.html`, `html/body.html` | `functions/<name>/html/head.html`, `html/body.html` |
| `css/styles.css` | `functions/<name>/css/styles.css` |
| `meta/diagnostics.json` | `functions/<name>/meta/diagnostics.json` |
| `meta/skipped-placeholder-ids.json` | `functions/<name>/meta/skipped-placeholder-ids.json` |
| `original/source.html` | `functions/<name>/original/source.html` |
| `assets/_index.json` | `functions/<name>/assets/_index.json` |
| 21 functional groups (activities, admin-panel, ads-studio, etc.) | Each group becomes a subfolder under `ids/` |

### 3.4 From `bardom-platform.zip` (v17-34)

| Feature | How we use it |
|---------|---------------|
| `SecurityShield` | Anti-decompile: signature verify, debugger detect, emulator detect, root detect |
| `LibraryInstallerWorker` | Downloads libraries from GitHub at first online run, stores locally for offline use |
| `FunctionsEngine` | Dynamic functions from Firebase — admin adds function → appears instantly in app + bot |
| `LocalStorage` (encrypted) | SharedPreferences with device ID, session, libs cache, inbox, points, FCM token |
| `BardomBuildManager` | In-app APK build trigger → GitHub Actions → download result |
| `AgentOrchestrator` | Background agent task queue (the "1000 agents" pattern) |
| `TelegramBotService` (foreground) | Long-polling bot running on the device itself |
| `BardomMessagingService` (FCM) | Push notifications from Firebase |
| `FirebaseRestClient` | Direct REST (no firebase_admin SDK needed) |
| `PointsManager` | Points system with min/max per function |
| `render-backend/server.js` | Express server: trigger builds, receive webhooks, relay to Firebase + Telegram |
| GitHub Actions `zip-build.yml` | Build APK from uploaded ZIP via repository_dispatch |
| ProGuard rules | Obfuscation + Log stripping + JS bridge protection |
| `secrets.properties` pattern | 15 BuildConfig fields injected at build time |
| `build.sh` raw mode | aapt2 + d8 + apksigner without Gradle (fallback) |
| Engine HTML (388 KB) | The full WebView UI loaded by MainActivity |

---

## 4. Target Project Architecture

```
bardom-universal-apk-generator/
├── main-apk/                          # The main APK (self-contained, offline-first)
│   ├── app/
│   │   ├── build.gradle               # minifyEnabled=true, ProGuard, signing
│   │   ├── proguard-rules.pro         # Obfuscation + Log stripping + bridge protection
│   │   ├── src/main/
│   │   │   ├── AndroidManifest.xml     # All permissions (declared once)
│   │   │   ├── java/com/bardom/universal/
│   │   │   │   ├── MainActivity.java           # WebView host + JS bridge
│   │   │   │   ├── SplashActivity.java         # Progress bar on first install
│   │   │   │   ├── SecurityShield.java         # Anti-decompile checks
│   │   │   │   ├── LibraryInstallerWorker.java # Downloads payload from GitHub
│   │   │   │   ├── PayloadManager.java         # Encrypts + stores GitHub payload
│   │   │   │   ├── AutoUpdater.java            # Checks GitHub for updates
│   │   │   │   ├── FunctionsEngine.java        # Dynamic functions (offline cache)
│   │   │   │   ├── LocalStorage.java            # Encrypted SharedPreferences
│   │   │   │   ├── ApkBuilderClient.java        # Talks to backend for APK builds
│   │   │   │   └── net/
│   │   │   │       ├── GitHubClient.java        # Fetches payload + updates
│   │   │   │       ├── FirebaseRestClient.java  # User data, points, builds
│   │   │   │       └── TelegramBotClient.java   # Bot communication
│   │   │   ├── assets/
│   │   │   │   ├── engine/index.html            # Bootstrap loader (tiny)
│   │   │   │   └── engine/loader.js             # Decrypts + injects payload
│   │   │   └── res/
│   │   │       ├── layout/activity_splash.xml   # Progress bar UI
│   │   │       ├── layout/activity_main.xml     # WebView container
│   │   │       ├── values/strings.xml
│   │   │       ├── values/colors.xml
│   │   │       └── mipmap-*/ic_launcher.png
│   │   └── google-services.json                 # Firebase config
│   ├── build.gradle
│   ├── settings.gradle
│   ├── gradle.properties
│   └── keystore.properties                       # Signing config (gitignored)
│
├── backend/                                    # Render backend (optional, for APK builds)
│   ├── engine/
│   │   ├── config.py
│   │   ├── function_registry.py
│   │   ├── code_extractor.py                    # Walks source, extracts IDs + strings
│   │   ├── config_json_processor.py             # Builds config.json per function
│   │   ├── strings_json_processor.py            # Builds strings.json per function
│   │   ├── template_renderer.py                 # Renders template.html
│   │   ├── project_generator.py                 # Android project tree per function
│   │   ├── apk_builder_v3.py                     # aapt2+javac+d8+apksigner from source
│   │   └── axml_builder.py                       # Binary AndroidManifest builder
│   ├── integrations/
│   │   ├── github_client.py                      # Push to repo, fetch updates
│   │   ├── render_client.py                      # Trigger deploys
│   │   ├── telegram_bot.py                       # Send messages + APKs
│   │   ├── firebase_client.py                   # Record builds, user data
│   │   └── zip_builder.py                        # Package project as zip
│   ├── app.py                                    # Flask API
│   └── requirements.txt
│
├── functions/                                   # Each function in its own folder
│   ├── calculator/
│   │   ├── function.json                        # Manifest (name, version, package, permissions)
│   │   ├── handler.py                           # Python logic (pure, no Android deps)
│   │   ├── template.html                        # HTML with {{ strings... }} / {{ config... }}
│   │   ├── config.json                          # ← auto-built: every ID + full code
│   │   ├── strings.json                         # ← auto-built: every string per ID, ordered
│   │   ├── rendered.html                        # ← auto-built: template + strings merged
│   │   ├── ids/                                 # ← one .html per ID, grouped
│   │   │   ├── _index.json
│   │   │   ├── main-ui/
│   │   │   │   ├── _index.json
│   │   │   │   ├── btnCalculate.html
│   │   │   │   └── ...
│   │   │   └── ...
│   │   ├── js/
│   │   │   ├── modules/
│   │   │   │   ├── calculate.js
│   │   │   │   └── history.js
│   │   │   └── globals/
│   │   ├── css/
│   │   │   └── style.css
│   │   ├── html/
│   │   │   ├── head.html
│   │   │   └── body.html
│   │   ├── assets/
│   │   │   └── _index.json
│   │   ├── meta/
│   │   │   ├── diagnostics.json
│   │   │   └── skipped-placeholder-ids.json
│   │   └── original/
│   │       └── source.html
│   ├── notes/
│   ├── todo_list/
│   ├── qr_generator/
│   ├── weather/
│   └── ... (unlimited functions)
│
├── scripts/
│   ├── build_all_metadata.py                    # Build config+strings+rendered for all
│   ├── build_apk_cli.py                         # Build one APK via CLI
│   ├── package_zip.py                           # Package entire project as zip
│   ├── push_github.py                           # Push to GitHub repo
│   ├── deploy_render.py                         # Trigger Render deploy
│   ├── create_render_service.py                 # Create new Render service
│   └── list_functions.py                        # List all function modules
│
├── android/tools/                               # Build tools (downloaded on demand)
│   ├── aapt2
│   ├── apksigner-lib.jar
│   ├── d8.jar
│   └── android.jar                              # Framework (API 34)
│
├── templates/                                   # 100 ready-to-build templates (from Universal_App_Generator)
│   ├── template_001_calculator.json
│   ├── ...
│   └── template_100_tax_estimator.json
│
├── docs/
│   └── SKILLS.md                                # This document
│
├── .env                                         # All credentials (NEVER committed)
├── .env.example                                 # Template (committed)
├── .gitignore
├── render.yaml                                  # Render deployment config
├── requirements.txt
├── setup.sh                                     # Detect Android SDK + JDK
├── start.sh                                     # Launch backend
└── README.md
```

---

## 5. The Universal APK Builder

### 5.1 Three Build Modes

The builder (`backend/engine/apk_builder_v3.py`) supports three modes, tried in order:

| Mode | When | How | Output |
|------|------|-----|--------|
| **v3 (from-source)** | Default — always preferred | aapt2 compile → link → javac → d8 → apksigner | Real APK, unique package/icon/name |
| **v2 (shell-based)** | Fallback if v3 tools missing | Replace assets in a real shell APK + re-sign | Real APK, fixed package |
| **v1 (webapk)** | Last resort — no Java at all | ZIP with rendered HTML + manifest.json | Installable ZIP (not a true APK) |

### 5.2 v3 Pipeline (Primary)

```
Source function folder
        │
        ▼
┌─────────────────────────────────────┐
│ 1. _prepare_project()               │  Create temp Android project tree
│    - AndroidManifest.xml            │  (unique package, label, version)
│    - res/values/strings.xml         │  (app_name from function manifest)
│    - res/values/colors.xml          │
│    - res/layout/activity_main.xml   │  (WebView container)
│    - res/mipmap-*/ic_launcher.png   │  (generated icon, colored by name hash)
│    - java/.../MainActivity.java     │  (WebView loads assets/webapp/index.html)
│    - assets/webapp/index.html       │  (rendered template)
│    - assets/webapp/config.json      │  (function's config.json)
│    - assets/webapp/strings.json     │  (function's strings.json)
│    - assets/webapp/css/ + js/        │  (function's CSS/JS)
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 2. _ensure_tools()                  │  Download on demand if missing:
│    - JDK 21 (Temurin, with javac)   │  /tmp/bardom-jdk/
│    - android.jar (API 34)           │  android/tools/android.jar
│    - aapt2 (build-tools 34)         │  android/tools/aapt2
│    - d8.jar                         │  android/tools/d8.jar
│    - apksigner-lib.jar              │  android/tools/apksigner-lib.jar
│    - debug.keystore (auto-created)  │  android/debug.keystore
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 3. aapt2 compile                    │  res/* → compiled.zip
│    aapt2 compile -o compiled.zip \   │
│       res/values/strings.xml \      │
│       res/values/colors.xml \       │
│       res/layout/activity_main.xml \│
│       res/mipmap-*/ic_launcher.png  │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 4. aapt2 link                       │  compiled.zip + manifest → linked.apk
│    aapt2 link -o linked.apk \       │  + generates R.java (resource IDs)
│       --manifest AndroidManifest.xml│  + --rename-manifest-package <pkg>
│       -I android.jar                │  + -A assets/ (bundles webapp)
│       --java gen/                   │  + --version-code / --version-name
│       --min-sdk-version 24         │
│       --target-sdk-version 34      │
│       --rename-manifest-package X   │
│       --auto-add-overlay            │
│       compiled.zip                  │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 5. javac                           │  MainActivity.java + R.java → .class
│    javac -source 17 -target 17 \    │
│       -classpath android.jar \      │
│       -d build/classes/ \           │
│       MainActivity.java R.java     │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 6. d8                              │  .class → classes.dex
│    java -cp d8.jar \                │
│       com.android.tools.r8.D8 \     │
│       --release --min-api 24 \      │
│       --output build/dex/ \         │
│       *.class                       │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 7. Inject dex                       │  Add classes.dex into linked.apk
│    zip -j linked.apk classes.dex   │  (re-zip with dex included)
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 8. apksigner sign                   │  v1 + v2 + v3 signing
│    java -jar apksigner.jar sign \   │
│       --ks debug.keystore \         │
│       --ks-key-alias bardom-debug \ │
│       --v1-signing-enabled true \   │
│       --v2-signing-enabled true \   │
│       --v3-signing-enabled true \   │
│       output.apk                    │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 9. apksigner verify                 │  Confirm signature is valid
│    java -jar apksigner.jar verify \ │
│       --verbose output.apk          │
└─────────────────────────────────────┘
        │
        ▼
    ✅ Real installable APK
       (unique package, unique icon,
        unique label, signed v2+v3)
```

### 5.3 Unlimited APK Guarantees

| Requirement | How it's met |
|-------------|--------------|
| Any function | `functions/<name>/` folder — add unlimited folders |
| Any content | `template.html` + `handler.py` + `css/` + `js/` per folder |
| Any size | aapt2 link + d8 handle arbitrary asset sizes (up to 2 GB per APK) |
| Any permissions | `function.json` declares permissions; manifest generator includes them |
| Unique package | `--rename-manifest-package com.bardom.app.<name>` per build |
| Unique icon | Generated PNG, color = MD5(name), drawn in 5 densities |
| Unique label | `strings.xml` `<string name="app_name">` = function's display name |
| Installable side-by-side | Different packages → no conflict on device |
| No rebuild of main APK | Main APK downloads function folders at runtime (see §6) |

---

## 6. The Main APK (Self-Contained, Offline-First)

### 6.1 Design Philosophy

The main APK is a **thin shell** that:

1. **Does not** bundle every function's HTML/CSS/JS at build time
2. **Does** show a progress bar on first launch and download the full payload from GitHub
3. **Encrypts** the payload locally so Apktool/Jadx cannot read it
4. **Works offline** after first download — no continuous backend dependency
5. **Checks for updates** periodically (background WorkManager job) — only connects when updates exist
6. **Connects to backend** only when a function requires server-side processing (e.g., AI generation, APK build)

### 6.2 First-Install Flow

```
User installs main APK
        │
        ▼
┌─────────────────────────────────────────┐
│ SplashActivity (progress bar)           │
│                                         │
│  Step 1/4: Checking GitHub for payload │  ◄── GitHubClient.fetchManifest()
│  Step 2/4: Downloading payload (XX MB) │  ◄── download to cache
│  Step 3/4: Decrypting + verifying      │  ◄── AES-256-GCM with device-bound key
│  Step 4/4: Storing encrypted locally   │  ◄── write to app/files/payload.enc
│                                         │
│  [████████████████░░░░░░] 72%          │
│  Stage: Decrypting...                   │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│ MainActivity (WebView)                  │
│                                         │
│  - Loads assets/engine/index.html       │  (tiny bootstrap, ~2 KB)
│  - index.html runs loader.js            │
│  - loader.js reads payload.enc          │
│  - Decrypts with device-bound key       │
│  - Injects decrypted HTML/CSS/JS        │
│  - Full UI appears                      │
└─────────────────────────────────────────┘
```

### 6.3 Payload Structure (Downloaded from GitHub)

The payload is a single encrypted blob containing the full `functions/` tree:

```
payload.enc (AES-256-GCM encrypted)
    │
    ▼ (decrypted in memory)
payload.json
{
  "version": "6.0.0",
  "functions": {
    "calculator": {
      "template_html": "<!DOCTYPE html>...",
      "config_json": "{...}",
      "strings_json": "{...}",
      "css": {"style.css": "..."},
      "js": {"app.js": "..."},
      "manifest": {"name": "Calculator", "package": "...", "permissions": [...]}
    },
    "notes": {...},
    "weather": {...},
    ...
  },
  "engine_html": "<!DOCTYPE html>...",  (the full engine UI, 388 KB)
  "templates": [...]                     (100 template definitions)
}
```

### 6.4 Update Flow (No APK Rebuild)

```
Background WorkManager (every 12 hours)
        │
        ▼
┌─────────────────────────────────────────┐
│ AutoUpdater.checkGitHub()               │
│  GET https://api.github.com/repos/      │
│      abuhoney/apk-generator-system/     │
│      contents/payload.manifest.json    │
│                                         │
│  Compare local version vs remote        │
└─────────────────────────────────────────┘
        │
        ├─ No update ──► do nothing (stays offline)
        │
        └─ Update available
                │
                ▼
        ┌─────────────────────────────────────┐
        │ Show notification: "Update ready"   │
        │ On next app open:                   │
        │   - Download new payload.enc        │
        │   - Decrypt + verify                │
        │   - Replace local payload.enc       │
        │   - Reload WebView                  │
        └─────────────────────────────────────┘
```

### 6.5 Backend Connectivity (Optional)

The main APK connects to the backend ONLY when:

| Action | Why backend is needed |
|--------|----------------------|
| Build a new APK from a function | Backend has aapt2/javac/d8/apksigner installed |
| AI code generation | Backend talks to OpenRouter (Kimi K2) |
| Record a build in Firebase | Audit trail |
| Send APK via Telegram | Backend has bot token |
| Push function to GitHub | Backend has GitHub token |

All other operations (viewing functions, using calculator/notes/weather) work **offline** with the locally-stored, encrypted payload.

---

## 7. Security & Anti-Decompilation

### 7.1 Threat Model

| Threat | Mitigation |
|--------|------------|
| Apktool decompiles APK → reads AndroidManifest, resources | ProGuard/R8 obfuscation + resource shrinking |
| Jadx decompiles classes.dex → reads Java source | ProGuard renames classes/methods/fields to `a`, `b`, `c` |
| Attacker reads `assets/webapp/*.html` (plain text) | **Payload is downloaded + encrypted at runtime** — not in the APK |
| Attacker reads `.env`, Firebase keys, bot tokens | **Secrets are NOT in the APK** — they live on the backend (Render env vars) |
| Attacker reads user data from SharedPreferences | `androidx.security:security-crypto` encrypts SharedPreferences |
| Attacher re-signs APK with their own key | `SecurityShield.verifySignature()` checks SHA-256 at startup |
| Attacker runs APK on emulator to debug | `SecurityShield.isEmulator()` detects common emulator signatures |
| Attacker attaches debugger | `SecurityShield.isDebuggerAttached()` checks `android.os.Debug.isDebuggerConnected()` |
| Attacher reads payload from `/data/data/.../files/` | Payload encrypted with AES-256-GCM; key derived from device ID + Android ID |

### 7.2 ProGuard Rules (from `bardom-platform.zip`)

```proguard
# Strip Log.v/d/i in release (keep w/e for crash reports)
-assumenosideeffects class android.util.Log {
    public static *** v(...);
    public static *** d(...);
    public static *** i(...);
}

# Obfuscate app code (rename to a, b, c)
-keep class com.bardom.universal.net.** { *; }   # keep network interfaces for JS bridge
-keepclassmembers class com.bardom.universal.MainActivity$EngineBridge {
    @android.webkit.JavascriptInterface <methods>;
}

# Keep Firebase / Gson / OkHttp (third-party libs need their symbols)
-keep class com.google.firebase.** { *; }
-keep class com.google.gson.** { *; }
-keep class okhttp3.** { *; }
```

### 7.3 Build Config (from `bardom-platform.zip` pattern)

```gradle
buildTypes {
    release {
        minifyEnabled true              // R8 obfuscation + shrinking
        shrinkResources true            // remove unused resources
        proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'),
                      'proguard-rules.pro'
        signingConfig signingConfigs.release
    }
}
```

### 7.4 Runtime Encryption (Payload)

```
Payload encryption flow:
    GitHub (plain JSON)
        │
        ▼ AES-256-GCM encrypt
    Encrypted blob (payload.enc)
        │
        ▼ stored in app/files/payload.enc
    Device filesystem (private mode)
        │
        ▼ on app launch, decrypted in memory
    WebView receives decrypted HTML

Key derivation:
    key = HKDF-SHA256(
        device_id      (UUID generated at first run)
        + android_id   (Settings.Secure.ANDROID_ID)
        + app_signature (SHA-256 of signing cert)
    )
    
    → Key is device-bound: payload encrypted on device A cannot be decrypted on device B
```

### 7.5 What an Attacker Sees After Decompiling

| What they look at | What they find |
|--------------------|----------------|
| `AndroidManifest.xml` | Obfuscated package, minimal permissions |
| `classes.dex` | Renamed classes (`a.b.c`), no readable method names |
| `res/values/strings.xml` | Just `app_name` — no secrets |
| `assets/engine/index.html` | Tiny bootstrap (2 KB) — just "Loading..." |
| `assets/engine/loader.js` | Decryption logic — but no key (key is derived at runtime) |
| SharedPreferences | Encrypted (AES-256-GCM via security-crypto) |
| `app/files/payload.enc` | Encrypted blob — useless without device-bound key |

**Result**: The attacker cannot reach `.env`, Firebase keys, bot tokens, user data, or per-user permissions — because none of those are in the APK. They live on the backend (Render env vars) or are encrypted with a device-bound key.

---

## 8. Function-Based Modular System

### 8.1 Function Folder Contract

Every function follows this exact structure (proven by the v3.1 modular output with 301 IDs / 372 functions):

```
functions/<function_name>/
├── function.json                  # MANDATORY: manifest
├── handler.py                      # OPTIONAL: Python logic (pure, no Android deps)
├── template.html                  # MANDATORY: HTML template with placeholders
├── config.json                    # AUTO-BUILT: every ID + full code
├── strings.json                   # AUTO-BUILT: every string per ID, ordered
├── rendered.html                  # AUTO-BUILT: template + strings merged
├── ids/                           # AUTO-BUILT: one .html per ID
│   ├── _index.json
│   └── <group>/
│       ├── _index.json
│       └── <id>.html
├── js/
│   ├── modules/
│   │   └── <module>.js
│   └── globals/
│       └── <global>.js
├── css/
│   └── style.css
├── html/
│   ├── head.html
│   └── body.html
├── assets/
│   └── _index.json
├── meta/
│   ├── diagnostics.json
│   └── skipped-placeholder-ids.json
└── original/
    └── source.html
```

### 8.2 `function.json` Schema

```json
{
  "name": "Calculator",
  "version": "1.0.0",
  "description": "A simple calculator with basic arithmetic operations",
  "package": "com.bardom.app.calculator",
  "entry": "template.html",
  "min_sdk": 24,
  "target_sdk": 34,
  "permissions": [
    "android.permission.INTERNET",
    "android.permission.ACCESS_NETWORK_STATE"
  ],
  "icon_color": "#58a6ff",
  "cost": 0,
  "min_points": 0,
  "max_uses_per_day": -1
}
```

### 8.3 Adding a New Function (No Rebuild)

```
1. Create functions/my_new_app/
2. Add function.json, template.html, handler.py, css/, js/
3. Run: python3 scripts/build_all_metadata.py --function my_new_app
   → generates config.json, strings.json, rendered.html, ids/
4. Push to GitHub: python3 scripts/push_github.py
5. Main APK's AutoUpdater detects new payload version
6. Next time user opens the app:
   - Downloads new payload.enc
   - Decrypts
   - "my_new_app" appears in the function list
   - User can build its APK via the backend
```

**No recompilation of the main APK ever needed.**

---

## 9. config.json / strings.json / template.html Processors

### 9.1 `config.json` Processor

**Purpose**: For every function folder, walks every source file and extracts every ID with its FULL code block (start → end, no truncation), preserving the branching structure.

**Supported source files**: `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.kt`, `.html`, `.htm`, `.css`, `.scss`, `.json`, `.xml`, `.gradle`, `.sh`, `.md`

**Extracted ID types**:
- Python: `def`, `class`, module-level constants, imports
- JavaScript/TypeScript: `function`, `class`, `const`/`let`/`var` (arrow + named)
- Java/Kotlin: `class`, `fun`/method, `object`, `interface`
- HTML/XML: `id=` attributes, `@+id/` references
- CSS: selectors + rule blocks
- JSON: every key (with dot-path: `parent.child[0].key`)
- Gradle: every call/assignment
- Shell: `function name()` blocks

**Output schema**:
```json
{
  "function": "calculator",
  "version": "1.0.0",
  "generated_at": "2026-09-18T...Z",
  "summary": {
    "files": 7,
    "ids": 42,
    "languages": ["python", "html", "css", "javascript"]
  },
  "files": [
    {
      "path": "handler.py",
      "language": "python",
      "lines": 142,
      "ids": [
        {
          "id": "calculate_total",
          "kind": "function",
          "line_start": 12,
          "line_end": 28,
          "code": "def calculate_total(...):\n    ...",
          "branch_of": null,
          "children": ["_validate_input", "_format_output"]
        }
      ]
    }
  ],
  "ids_index": {
    "calculate_total": {
      "file": "handler.py",
      "line_start": 12,
      "line_end": 28,
      "kind": "function",
      "branch_of": null
    }
  },
  "tree": {
    "calculate_total": {
      "_meta": {"kind": "function", "file": "handler.py", "line_start": 12, "line_end": 28},
      "_code_ref": "calculate_total",
      "children": {
        "_validate_input": {
          "_meta": {...},
          "_code_ref": "_validate_input",
          "children": {}
        }
      }
    }
  }
}
```

**Branching**: Sub-functions point to their parent via `branch_of`; the parent's `children` array lists them back. The `tree` is the hierarchical view; `ids_index` is the flat lookup; `files[].ids[].code` holds the full code (stored once, referenced by `_code_ref` to avoid duplication).

### 9.2 `strings.json` Processor

**Purpose**: For every function folder, extracts every string literal — quoted strings, XML text content, JSON values — in the exact order they appear in each source file, grouped by the ID they belong to.

**Output schema**:
```json
{
  "function": "calculator",
  "version": "1.0.0",
  "generated_at": "2026-09-18T...Z",
  "summary": {
    "files": 7,
    "total_strings": 87,
    "ids_with_strings": 12
  },
  "global_strings": [
    {"text": "Calculator", "file": "handler.py", "line": 1}
  ],
  "by_id": {
    "calculate_total": [
      {"text": "Total amount", "file": "handler.py", "line": 14},
      {"text": "Invalid input", "file": "handler.py", "line": 18}
    ]
  },
  "ordered": [
    {"text": "Calculator", "file": "handler.py", "line": 1, "id": null},
    {"text": "Total amount", "file": "handler.py", "line": 14, "id": "calculate_total"}
  ]
}
```

### 9.3 `template.html` Renderer

**Purpose**: Renders a function's `template.html` using its `config.json` + `strings.json`, producing the final `rendered.html` that ships inside the APK's `assets/webapp/`.

**Supported placeholders** (minimal template engine, no third-party deps):

| Syntax | Example | Behavior |
|--------|---------|----------|
| `{{ a.b.c }}` | `{{ config.function }}` | Dot-path lookup |
| `{{ a.b[0].c }}` | `{{ strings.by_id.calculate[0].text }}` | Index lookup |
| `{{#if var}}...{{/if}}` | `{{#if config.summary.ids}}...{{/if}}` | Conditional block |
| `{{#each list}}...{{/each}}` | `{{#each strings.ordered}}<li>{{this.text}}</li>{{/each}}` | Loop with `{{this}}` + `{{@index}}` |

**Example template.html**:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <title>{{ config.function }} — {{ strings.global_strings[0].text }}</title>
  <link rel="stylesheet" href="css/style.css">
</head>
<body>
  <h1>{{ config.function }}</h1>
  <p>Version: {{ config.version }}</p>
  <ul>
    {{#each strings.by_id.calculate}}
      <li>{{ this.text }}</li>
    {{/each}}
  </ul>
  <script src="js/app.js"></script>
</body>
</html>
```

---

## 10. Backend (Render) Role

### 10.1 When the Backend is Needed

| Operation | Backend required? |
|-----------|-------------------|
| View function list | ❌ Offline (from encrypted payload) |
| Use calculator/notes/weather | ❌ Offline |
| Build a new APK | ✅ Backend (has aapt2/javac/d8/apksigner) |
| AI code generation | ✅ Backend (talks to OpenRouter) |
| Push to GitHub | ✅ Backend (has GitHub token) |
| Send APK via Telegram | ✅ Backend (has bot token) |
| Record build in Firebase | ✅ Backend |
| Auto-update check | ❌ Direct GitHub API (no backend) |

### 10.2 Backend Endpoints

```
GET  /api/health                    — Health check
GET  /api/config                    — Safe config (secrets redacted)
GET  /api/functions                 — List all functions
GET  /api/functions/<name>          — Function detail
POST /api/build-config-json         — Build config.json for one function
POST /api/build-strings-json        — Build strings.json for one function
POST /api/build-templates           — Render template.html
POST /api/build-all-metadata        — Build everything for all functions
POST /api/build-apk                 — Build a real APK (v3 pipeline)
GET  /api/apks                      — List built APKs
GET  /download/<fn>/<file>           — Download a built APK
POST /api/github/push               — Push to GitHub repo
POST /api/render/deploy             — Trigger Render deploy
POST /api/telegram/notify           — Send Telegram message
GET  /api/render/health             — Render service status
GET  /api/firebase/builds           — Builds recorded in Firebase
POST /api/package-zip               — Package entire project as zip
```

### 10.3 Backend Tool Auto-Install

The backend (on Render free tier) auto-downloads its build tools on first use:

| Tool | Source | Cached at |
|------|--------|-----------|
| JDK 21 (with javac) | Temurin GitHub releases | `/tmp/bardom-jdk/` |
| android.jar (API 34) | Google platform-34-ext10 zip | `android/tools/android.jar` |
| aapt2 | build-tools_r34 zip | `android/tools/aapt2` |
| d8.jar | build-tools_r34 zip | `android/tools/d8.jar` |
| apksigner-lib.jar | build-tools_r34 zip | `android/tools/apksigner-lib.jar` |
| debug.keystore | keytool (auto-generated) | `android/debug.keystore` |

The JRE path is persisted to `/tmp/bardom-jdk/java_path.txt` so subsequent requests don't re-download.

---

## 11. GitHub Integration

### 11.1 Repo Structure

```
abuhoney/apk-generator-system/         (NEW repo — does NOT touch existing files)
├── main-apk/                          (the main APK source)
├── backend/                           (Render backend source)
├── functions/                         (all function folders)
├── scripts/                           (CLI scripts)
├── templates/                         (100 ready-to-build templates)
├── docs/SKILLS.md                     (this document)
├── .env.example                       (template, committed)
├── render.yaml
├── requirements.txt
├── setup.sh
├── start.sh
└── README.md
```

### 11.2 Payload Distribution

The main APK fetches its encrypted payload from GitHub:

```
GET https://api.github.com/repos/abuhoney/apk-generator-system/contents/payload.enc
    Headers: Authorization: token <github_token>

→ Base64-decode the content
→ Decrypt with device-bound key
→ Inject into WebView
```

### 11.3 Update Detection

```
GET https://api.github.com/repos/abuhoney/apk-generator-system/contents/payload.manifest.json
    → {"version": "6.0.0", "sha": "...", "size": 1234567}

Compare with local stored version.
If different → download new payload.enc → re-encrypt with device key → store
```

### 11.4 GitHub Actions CI/CD (from `bardom-platform.zip`)

Two workflows (adopted from the bardom-platform reference):

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `build-platform.yml` | Push to `main` (paths: `app/**`, `build.gradle`, etc.) | Build the main APK with JDK 17 + Android SDK 34 + Gradle 8.5, upload to Releases |
| `zip-build.yml` | `repository_dispatch` (event_type: `bardom_zip_build`) | Build an APK from an uploaded ZIP — downloads from Firebase, unzips, builds, uploads to Releases |

---

## 12. Telegram Bot Integration

### 12.1 Bot Commands (from `bardom-platform.zip` `bot.py`)

| Command | Function |
|---------|----------|
| `/start` | Link account or reward link |
| `/link` | Linking instructions |
| `/points` | Show balance |
| `/functions` | List dynamic functions |
| `/invite` | Generate invite link |
| `/inbox` | Show messages |
| `/buy` | Buy points with Stars |
| `/Bardom` | Build APK from ZIP |
| `/cancel` | Cancel ZIP upload |
| `/add_points UID AMOUNT` | Admin: add points |
| `/newfunc ID TYPE TITLE COST` | Admin: create function |
| `/announce TEXT` | Admin: broadcast |

### 12.2 In-App Bot (from `bardom-platform.zip`)

The main APK runs a **foreground Telegram bot service** (`TelegramBotService.java`) — long-polling on the device itself. This enables:
- Push notifications even when app is closed
- Bot commands work without backend
- FCM + bot notifications in parallel

### 12.3 Credentials

```
API_ID=28635681
API_HASH=9ab1acca768da671ab3f16eff541d999
BOT_TOKEN=8323866821:AAEebHmI-Z8BGoWLz2v27p7Cnim8knk-0aI
TELEGRAM_ADMIN_CHAT_ID=7082122839
BOT_USERNAME=allArabservicesbot
```

These live **only on the backend** (Render env vars) and in the `bot.py` (server-side). They are **never** compiled into the main APK.

---

## 13. Firebase Integration

### 13.1 What Firebase Stores

| Path | Content |
|------|---------|
| `/users/<uid>` | User profile (username, email, points, referralCode, linkCode) |
| `/functions/<funcId>` | Dynamic function definition (type, cost, min, max, title, enabled) |
| `/build_queue/<buildId>` | Build status + progress (for APK builds via GitHub Actions) |
| `/inbox/<uid>/<msgId>` | User-to-user messages |
| `/announcements` | Broadcast messages |
| `/fcm_tokens/<uid>` | Device FCM tokens for push notifications |

### 13.2 REST API (no SDK)

From `bardom-platform.zip` `FirebaseRestClient.java` — uses direct HTTPS REST, no `firebase_admin` dependency:

```java
// GET
URL url = new URL(FIREBASE_DB_URL + "/users/" + uid + ".json");
HttpsURLConnection con = (HttpsURLConnection) url.openConnection();
con.setRequestMethod("GET");
String response = readStream(con.getInputStream());

// PUT
con.setRequestMethod("PUT");
con.setRequestProperty("Content-Type", "application/json");
con.setDoOutput(true);
con.getOutputStream().write(jsonBody.getBytes("UTF-8"));
```

### 13.3 Credentials

```
FIREBASE_API_KEY=AIzaSyBm-ZwOv8oPd_0rms_2oesGz3fDmt5ogvA
FIREBASE_APP_ID=1:1002499268790:web:9437bee4f4df9f93adc617
FIREBASE_AUTH_DOMAIN=all-arab-services-750ad.firebaseapp.com
FIREBASE_DATABASE_URL=https://all-arab-services-750ad-default-rtdb.europe-west1.firebasedatabase.app
FIREBASE_PROJECT_ID=all-arab-services-750ad
```

---

## 14. Build Pipeline

### 14.1 Build the Main APK (One-Time)

```bash
# On a machine with Android SDK + JDK 17
cd main-apk/
./gradlew assembleRelease
# Output: app/build/outputs/apk/release/app-release.apk
```

This APK is then distributed to users. It is **never rebuilt** unless the core shell changes.

### 14.2 Build a Function APK (Unlimited, On-Demand)

**Via the main APK UI**:
1. User opens main APK
2. Selects a function (e.g., "Calculator")
3. Taps "Build APK"
4. Main APK sends POST to backend `/api/build-apk`
5. Backend runs the v3 pipeline (aapt2 + javac + d8 + apksigner)
6. Backend returns the APK
7. Main APK downloads it to `Download/` folder
8. User installs it

**Via CLI**:
```bash
python3 scripts/build_apk_cli.py calculator
# Output: _output/calculator/Calculator.apk (signed v2+v3)
```

**Via Telegram bot**:
```
User: /Bardom
Bot: Send me a ZIP of your project
User: [sends ZIP]
Bot: Building... [progress bar]
Bot: [sends APK back]
```

### 14.3 Build from a Sketchware HTML (via `waw.html`)

1. Open `waw.html` in a browser
2. Drag-drop a Sketchware HTML file
3. Click "Extract + Generate"
4. waw.html:
   - Runs 13 self-tests
   - Extracts every ID, string, function
   - Generates Kotlin/Java/Gradle files
   - Builds a complete Android project
   - Optionally pushes to GitHub, triggers Render, notifies Telegram
5. The output is a modular project zip (exactly like `sketchware_app_generator (17)_modular_project_v3_1.zip`)

---

## 15. Auto-Update Mechanism

### 15.1 Update Detection

```
WorkManager periodic job (every 12 hours):
    AutoUpdater.checkGitHub()
        │
        ├─ GET github.com/.../contents/payload.manifest.json
        ├─ Compare version with local
        │
        ├─ Same version → do nothing (stay offline)
        └─ New version → show notification "Update available"
                          │
                          ▼ (on next app open)
            Download new payload.enc
            Decrypt + verify
            Replace local payload.enc
            Reload WebView
            New functions/templates appear instantly
```

### 15.2 What Can Be Updated Without Rebuilding the APK

| What | How |
|------|-----|
| New functions | Add folder to `functions/`, rebuild payload, push to GitHub |
| Updated function HTML/CSS/JS | Edit files in `functions/`, rebuild payload |
| New templates | Add to `templates/`, rebuild payload |
| New strings | Edit `strings.json` in function folder, rebuild payload |
| Updated engine UI | Edit `engine.html`, rebuild payload |
| New bot commands | Edit `bot.py` on backend (no APK change) |
| New backend endpoints | Edit `backend/app.py`, redeploy Render (no APK change) |

### 15.3 What Requires an APK Rebuild

Only changes to the **main APK shell** itself:
- `MainActivity.java` changes (new JS bridge methods)
- `AndroidManifest.xml` changes (new permissions)
- `SecurityShield.java` changes
- `build.gradle` dependency changes
- ProGuard rules changes

These happen rarely (once every few months).

---

## 16. Self-Test Suite

### 16.1 The 13 Tests (from `waw.html`)

Adopted as the verification suite for the modular extractor:

| # | Test | What it verifies |
|---|------|------------------|
| 1 | ID extraction | Every `id=` attribute captured |
| 2 | String extraction | Every quoted string captured, ordered |
| 3 | Function extraction | Every `function`/`def`/`class` captured with full body |
| 4 | Branching | Sub-functions point to parent correctly |
| 5 | config.json valid JSON | Schema correct, no truncation |
| 6 | strings.json valid JSON | All strings present, ordered |
| 7 | template.html renders | Placeholders resolve correctly |
| 8 | aapt2 compile succeeds | Resources compile |
| 9 | aapt2 link succeeds | APK links with correct package |
| 10 | javac succeeds | Java compiles |
| 11 | d8 succeeds | Dex created |
| 12 | apksigner verifies | Signature valid (v2+v3) |
| 13 | APK installs on emulator | Package parser accepts it |

### 16.2 Running Self-Tests

```bash
# Backend self-test
python3 -m engine.self_test

# CLI per-function build test
python3 scripts/build_apk_cli.py <function> --json

# Full 100-template sweep (from Universal_App_Generator)
python3 cli.py self-test
```

---

## 17. Deployment Plan

### 17.1 Phase 1: Backend (Render)

```bash
# 1. Push to GitHub (new repo — no overwrite of existing)
python3 scripts/push_github.py

# 2. Create Render service
python3 scripts/create_render_service.py --name bardom-universal-apk

# 3. Set env vars on Render (via dashboard or API)
#    All secrets from .env

# 4. Trigger first deploy
python3 scripts/deploy_render.py
```

### 17.2 Phase 2: Main APK

```bash
# 1. Build the main APK (one-time)
cd main-apk/
./gradlew assembleRelease

# 2. Sign with release keystore
apksigner sign --ks release.keystore app-release.apk

# 3. Distribute to users (direct download, Telegram, etc.)
```

### 17.3 Phase 3: Functions (Ongoing)

```bash
# Add a new function
mkdir functions/my_new_app/
# ... add function.json, template.html, handler.py, css/, js/

# Build its metadata
python3 scripts/build_all_metadata.py --function my_new_app

# Build its APK (via backend)
curl -X POST https://<backend>/api/build-apk \
  -H "Content-Type: application/json" \
  -d '{"function": "my_new_app"}'

# Push to GitHub (auto-update triggers on main APK)
python3 scripts/push_github.py
```

### 17.4 Phase 4: Bot

```bash
# Deploy bot.py on Render (separate service) or locally
pip install -r requirements.txt
python3 bot.py
```

---

## 18. File Tree (Final Project)

```
bardom-universal-apk-generator/
│
├── main-apk/                                    # The self-contained, offline-first APK
│   ├── app/
│   │   ├── build.gradle                          # minifyEnabled=true, ProGuard, signing
│   │   ├── proguard-rules.pro                   # Obfuscation + Log stripping + bridge protection
│   │   ├── google-services.json                 # Firebase config
│   │   └── src/main/
│   │       ├── AndroidManifest.xml              # All permissions declared once
│   │       ├── java/com/bardom/universal/
│   │       │   ├── MainActivity.java             # WebView host + JS bridge
│   │       │   ├── SplashActivity.java           # Progress bar on first install
│   │       │   ├── SecurityShield.java           # Anti-decompile (sig + debugger + emulator)
│   │       │   ├── LibraryInstallerWorker.java   # Downloads payload from GitHub
│   │       │   ├── PayloadManager.java           # Encrypts + stores payload
│   │       │   ├── AutoUpdater.java              # Checks GitHub for updates (12h interval)
│   │       │   ├── FunctionsEngine.java          # Dynamic functions (offline cache)
│   │       │   ├── LocalStorage.java             # Encrypted SharedPreferences
│   │       │   ├── ApkBuilderClient.java         # Talks to backend for APK builds
│   │       │   ├── BardomApp.java                # Application class
│   │       │   ├── AgentOrchestrator.java        # Background agent task queue
│   │       │   └── net/
│   │       │       ├── GitHubClient.java          # Fetches payload + updates
│   │       │       ├── FirebaseRestClient.java   # User data, points, builds
│   │       │       └── TelegramBotClient.java     # Bot communication
│   │       ├── assets/engine/
│   │       │   ├── index.html                     # Bootstrap loader (2 KB)
│   │       │   └── loader.js                      # Decrypts + injects payload
│   │       └── res/
│   │           ├── layout/
│   │           │   ├── activity_splash.xml       # Progress bar UI
│   │           │   └── activity_main.xml          # WebView container
│   │           ├── values/strings.xml
│   │           ├── values/colors.xml
│   │           ├── values/styles.xml
│   │           ├── values-ar/strings.xml         # Arabic strings
│   │           ├── mipmap-hdpi/ic_launcher.png
│   │           ├── mipmap-xhdpi/ic_launcher.png
│   │           ├── mipmap-xxhdpi/ic_launcher.png
│   │           ├── mipmap-xxxhdpi/ic_launcher.png
│   │           └── xml/
│   │               ├── network_security_config.xml
│   │               └── file_paths.xml
│   ├── build.gradle
│   ├── settings.gradle
│   ├── gradle.properties
│   ├── keystore.properties                       # Signing config (gitignored)
│   └── secrets.properties                        # BuildConfig fields (gitignored)
│
├── backend/                                      # Render backend (optional, for APK builds)
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── config.py                              # Loads .env credentials
│   │   ├── function_registry.py                  # Discovers function folders
│   │   ├── code_extractor.py                     # Walks source, extracts IDs + strings
│   │   ├── config_json_processor.py              # Builds config.json per function
│   │   ├── strings_json_processor.py             # Builds strings.json per function
│   │   ├── template_renderer.py                  # Renders template.html
│   │   ├── project_generator.py                  # Android project tree per function
│   │   ├── apk_builder.py                         # v1 webapk fallback
│   │   ├── apk_builder_v2.py                     # v2 shell-based builder
│   │   ├── apk_builder_v3.py                     # v3 from-source builder (primary)
│   │   ├── axml_builder.py                        # Binary AndroidManifest builder
│   │   └── self_test.py                           # End-to-end test runner
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── github_client.py                       # Push to repo, fetch updates
│   │   ├── render_client.py                       # Trigger deploys
│   │   ├── telegram_bot.py                        # Send messages + APKs
│   │   ├── firebase_client.py                     # Record builds, user data
│   │   └── zip_builder.py                         # Package project as zip
│   ├── routes/
│   │   └── __init__.py
│   ├── utils/
│   │   └── __init__.py
│   ├── app.py                                     # Flask API (all endpoints)
│   └── requirements.txt                           # flask + gunicorn only
│
├── functions/                                    # Each function in its own folder
│   ├── calculator/                               # Example: Calculator
│   │   ├── function.json
│   │   ├── handler.py
│   │   ├── template.html
│   │   ├── config.json                            # auto-built
│   │   ├── strings.json                          # auto-built
│   │   ├── rendered.html                         # auto-built
│   │   ├── ids/                                  # auto-built, one .html per ID
│   │   │   ├── _index.json
│   │   │   └── <group>/<id>.html
│   │   ├── js/
│   │   │   ├── modules/<module>.js
│   │   │   └── globals/<global>.js
│   │   ├── css/style.css
│   │   ├── html/
│   │   │   ├── head.html
│   │   │   └── body.html
│   │   ├── assets/_index.json
│   │   ├── meta/
│   │   │   ├── diagnostics.json
│   │   │   └── skipped-placeholder-ids.json
│   │   └── original/source.html
│   ├── notes/
│   ├── todo_list/
│   ├── qr_generator/
│   ├── weather/
│   └── ... (unlimited — add as many as needed)
│
├── scripts/
│   ├── __init__.py
│   ├── build_all_metadata.py                     # Build config+strings+rendered for all
│   ├── build_apk_cli.py                          # Build one APK via CLI
│   ├── package_zip.py                            # Package entire project as zip
│   ├── push_github.py                            # Push to GitHub repo
│   ├── deploy_render.py                          # Trigger Render deploy
│   ├── create_render_service.py                  # Create new Render service
│   └── list_functions.py                         # List all function modules
│
├── android/tools/                                # Build tools (downloaded on demand)
│   ├── aapt2                                     # Resource compiler/linker
│   ├── apksigner-lib.jar                         # APK signer (v1+v2+v3)
│   ├── d8.jar                                    # Dex compiler
│   └── android.jar                               # Framework (API 34)
│
├── templates/                                    # 100 ready-to-build templates
│   ├── template_001_calculator.json
│   ├── template_002_notes.json
│   ├── ...
│   └── template_100_tax_estimator.json
│
├── docs/
│   └── SKILLS.md                                 # This document
│
├── .github/workflows/
│   ├── build-platform.yml                        # Build main APK (JDK 17 + SDK 34 + Gradle 8.5)
│   └── zip-build.yml                             # Build APK from uploaded ZIP
│
├── render-backend/                               # Alternative Node.js backend (from bardom-platform)
│   ├── src/server.js
│   └── package.json
│
├── bot.py                                        # Telegram bot (Pyrogram, from bardom-platform)
├── .env                                          # All credentials (NEVER committed)
├── .env.example                                  # Template (committed)
├── .gitignore
├── render.yaml                                   # Render deployment config
├── requirements.txt                              # Python deps (flask + gunicorn + pyrogram)
├── setup.sh                                      # Detect Android SDK + JDK
├── start.sh                                      # Launch backend
├── build.sh                                      # Build main APK (Gradle + raw modes)
└── README.md
```

---

## 19. Glossary

| Term | Definition |
|------|------------|
| **Main APK** | The self-contained shell APK installed on the user's phone. Downloads encrypted payload from GitHub at first launch. |
| **Function APK** | An APK built for a specific function (e.g., Calculator, Notes). Built on-demand by the backend. |
| **Payload** | The encrypted blob containing all function folders (HTML/CSS/JS/config/strings). Downloaded from GitHub, stored locally encrypted. |
| **Payload manifest** | A small JSON on GitHub with `version`, `sha`, `size`. Used by AutoUpdater to detect changes. |
| **Device-bound key** | AES-256-GCM key derived from `device_id + android_id + app_signature`. Ensures payload can only be decrypted on the original device. |
| **Function folder** | A folder under `functions/` containing one complete function: manifest, template, handler, config, strings, CSS, JS. |
| **config.json** | Auto-built file listing every ID in the function folder, with full code blocks and branching structure. |
| **strings.json** | Auto-built file listing every string per ID, in source order. |
| **template.html** | The function's HTML template with `{{ config... }}` / `{{ strings... }}` placeholders. |
| **rendered.html** | The final HTML produced by rendering template.html with config.json + strings.json. Ships inside the function APK's `assets/webapp/`. |
| **v3 builder** | The primary APK builder: aapt2 compile → link → javac → d8 → apksigner. Produces real installable APKs with unique package/icon/name. |
| **v2 builder** | Fallback builder: replaces assets in a shell APK + re-signs. Fixed package. |
| **v1 builder** | Last-resort builder: produces a webapk (ZIP with HTML). Not a true APK. |
| **AutoUpdater** | WorkManager periodic job (12h) that checks GitHub for payload updates and downloads them if available. |
| **SecurityShield** | Anti-decompile module: signature verification, debugger detection, emulator detection, root detection. |
| **LibraryInstallerWorker** | Downloads required libraries from GitHub at first online run (from bardom-platform pattern). |
| **FunctionsEngine** | Dynamic functions engine: reads functions from Firebase, executes locally (add_points, purchase, reward_link, etc.). |
| **AgentOrchestrator** | Background agent task queue — the "1000 agents" pattern for parallel work. |

---

**End of SKILLS.md**

This document is the complete specification for the BardomPro Universal APK Generator. It is the single source of truth for the project's architecture, features, security model, and build pipeline. All implementation must conform to this specification.
