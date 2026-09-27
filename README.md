#  Beacon

### Simplifying Engineering Overhead

**Beacon** is an offline engineering productivity workspace built with **Python, PySide6, and SQLite**.

It brings project management, requirements, files, planning, notes, meetings, people, links, and everyday engineering tools into a single desktop application.

---

## ✨ Features

### 📁 Project Management

* Create and manage engineering projects
* Project codes and owners
* Start/end dates
* Project status
* Project hold/close management
* Project-specific file storage

### 📋 Requirements

* Functional
* Performance
* Safety
* Interface
* Constraint

Requirement lifecycle:

`Draft → Reviewed → Approved → Implemented → Verified`

Verification methods:

`Test • Analysis • Inspection • Demonstration`

### 👥 People & Roles

Built-in roles:

* Head
* Program Manager
* Manager
* System Engineer
* Developer
* Tester

Role-based capabilities control access to project features.

### 📅 Planning & Meetings

* Daily task planning
* Task reminders
* Meeting information
* Meeting links
* Meeting location
* Organizer information
* Minutes of Meeting (MoM)

### 📝 Notes

Beacon supports both:

* Daily notes
* Rich engineering notes

Notes can contain purpose, place, content, creation time, and update time.

### 📂 Engineering Files

Beacon organizes common engineering file types, including:

```text
MATLAB / Simulink
C / C++
Python
Excel / CSV
Word
PowerPoint
PDF
Images
Text / Logs
Archives
```

### 🔗 Engineering Links

Keep frequently used URLs in one place:

* Documentation
* Project portals
* Git repositories
* Engineering tools
* Reference material

### 🚀 Application Launcher

Quick access to installed applications such as:

* VS Code
* Outlook
* Teams
* Excel
* Word
* Notepad
* Calculator
* File Explorer

### 🕘 Recent Files

Beacon maintains a bounded list of recently opened files for quick access.

### 📥 Download Monitoring

Beacon can monitor commonly used folders such as:

* Downloads
* Desktop
* Documents
* OneDrive

Temporary download files are detected separately.

---

## 🎨 UI

Beacon uses a modern PySide6/Qt interface with multiple themes:

* Slate
* Graphite
* Navy
* Forest

The Home page provides a centralized engineering workspace with project tiles, planning, meetings, recent files, and quick-access tools.

---

## 🏗️ Architecture

```text
                    ┌─────────────────────┐
                    │       Beacon        │
                    │    Desktop App      │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        ┌───────────┐    ┌────────────┐   ┌─────────────┐
        │  PySide6  │    │   SQLite   │   │ File System │
        │    /Qt    │    │  Database  │   │   /Projects │
        └───────────┘    └────────────┘   └─────────────┘
                               │
                               ▼
                       Local Application
                            Data
```

---

## 💾 Data Storage

Beacon intentionally separates the live database from project files.

### Application Database

```text
%LOCALAPPDATA%\Beacon\beacon.db
```

The SQLite database is kept locally rather than inside a synchronized OneDrive directory.

### Project Files

When OneDrive is available:

```text
OneDrive\Beacon\Projects
```

Otherwise:

```text
Documents\Beacon\Projects
```

This separation helps avoid SQLite synchronization problems.

---

## 🛠️ Technology Stack

| Technology  | Purpose           |
| ----------- | ----------------- |
| Python      | Application logic |
| PySide6     | Desktop GUI       |
| Qt          | UI framework      |
| SQLite      | Local database    |
| PyInstaller | Windows packaging |

---

## 🚀 Run from Source

Clone the repository:

```bash
git clone https://github.com/<your-username>/Beacon.git
cd Beacon
```

Run:

```bash
python beacon_25.py
```

If you have multiple Python installations:

```powershell
& "C:\Path\To\python.exe" beacon_25.py
```

---

## 📦 Build Windows Application

Beacon uses a PyInstaller specification file.

```powershell
python -m PyInstaller --noconfirm --clean beacon.spec
```

The packaged application will be generated according to the configuration in `beacon.spec`.

For a specific Python installation:

```powershell
& "C:\Path\To\python.exe" -m PyInstaller --noconfirm --clean beacon.spec
```

---

## 🗄️ Database Migration

Beacon maintains compatibility with existing databases through schema migration.

For example, when new columns are introduced, the application checks the existing SQLite schema and adds missing columns rather than requiring the user to delete the database.

This allows application upgrades while preserving existing project data.

---

## 📸 Screenshots

Add screenshots here:

```markdown
![Beacon Home](screenshots/home.png)

![Project Management](screenshots/projects.png)

![Requirements](screenshots/requirements.png)
```

Recommended repository structure:

```text
Beacon/
│
├── beacon_25.py
├── beacon.spec
├── README.md
│
├── screenshots/
│   ├── home.png
│   ├── projects.png
│   └── requirements.png
│
└── ...
```

---

## 🗺️ Roadmap

* [ ] Database version management
* [ ] Automated database backup/restore
* [ ] Advanced project dashboards
* [ ] Requirement traceability
* [ ] Enhanced calendar integration
* [ ] Global project search
* [ ] Project health dashboard
* [ ] Engineering reports
* [ ] Import/export tools
* [ ] Additional engineering tool integrations

---

## 🤝 Contributing

Contributions, ideas, and improvements are welcome.

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature/my-feature
```

3. Commit your changes

```bash
git commit -m "Add my feature"
```

4. Push the branch

```bash
git push origin feature/my-feature
```

5. Open a Pull Request

---

## 📄 License

Add your preferred license here.

Example:

```text
Copyright © 2026 Beacon

All rights reserved.
```

---

## 🔦 Beacon

> **One workspace. Less overhead. Better engineering.**
