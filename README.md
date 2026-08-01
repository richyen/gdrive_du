# gdrive-du

Crawl a **Google Shared Drive** you select and report:

- **`du`-style folder sizes** — total bytes per folder, deepest-first, like `du`.
- **`tree`-style listing** — an indented tree with sizes per node.
- A **web UI** with an interactive, collapsible tree, size bars, and a sortable size table.

Both a **CLI** and a **web UI** are included.

## How it works

The app fetches every item in the shared drive via the Drive API (one paginated
listing), builds an in-memory tree from each file's `parents`, and sums file
sizes up the tree. Read-only access only (`drive.readonly`).

> **Note on Google-native files:** Google Docs / Sheets / Slides report *no*
> `size` because they don't consume Drive storage quota. They are counted as
> **0 bytes** (but still counted as files). Uploaded/binary files report true sizes.

## 1. Setup — Google OAuth client

1. Go to the [Google Cloud Console](https://console.cloud.google.com/), create (or pick) a project.
2. Enable the **Google Drive API** (APIs & Services → Library → Google Drive API → Enable).
3. Configure the **OAuth consent screen** (User type: Internal if you're on Workspace, else External + add yourself as a test user).
4. APIs & Services → **Credentials → Create Credentials → OAuth client ID → Application type: Desktop app**.
5. **Download the JSON** and save it in this folder as **`credentials.json`**.

On first run a browser window opens for consent; a `token.json` is then cached
so you won't be prompted again.

## 2. Install

```powershell
pip install -r requirements.txt
```

## 3. CLI usage

```powershell
# List the shared drives you can access
python -m gdrive_du.cli drives

# du-style folder sizes (interactive drive picker if -d omitted)
python -m gdrive_du.cli du
python -m gdrive_du.cli du -d "Marketing Team"        # by name or drive id
python -m gdrive_du.cli du -a                          # include individual files
python -m gdrive_du.cli du -L 2                         # limit depth to 2
python -m gdrive_du.cli du --bytes                      # raw bytes, not human-readable

# tree-style listing
python -m gdrive_du.cli tree -d "Marketing Team"
python -m gdrive_du.cli tree --folders-only --no-size
python -m gdrive_du.cli tree -L 3

# Save a snapshot once, then render offline (no re-crawl)
python -m gdrive_du.cli crawl -d "Marketing Team" -o marketing.json
python -m gdrive_du.cli du   --load marketing.json
python -m gdrive_du.cli tree --load marketing.json
```

Common flags: `-d/--drive`, `-L/--max-depth`, `-b/--bytes`, `--include-trashed`,
`--load <snapshot.json>`. `du` adds `-a/--all`; `tree` adds `--folders-only` and `--no-size`.

## 4. Web UI

```powershell
python -m gdrive_du.web            # serves http://127.0.0.1:5000
python -m gdrive_du.web --port 8080
```

Then open the URL, pick a shared drive from the dropdown, and click **Crawl**.
Switch between the **Tree** and **du (sizes)** tabs. Results are cached in the
server process per drive; use **Refresh** to force a re-crawl.

- **Hover a file's 📄 icon** to see its **md5 checksum**, modified time, and size.
  (md5 is also included in the crawl/snapshot JSON for every binary file.)
- **Downloads** are gated by the **"allow downloads"** switch in the header. It
  is **off by default and enforced server-side** — while off, the download
  endpoint returns HTTP 403. Turn it on to reveal a ⬇ button on each file.
  Google-native docs are exported on download (Docs→`.docx`, Sheets→`.xlsx`,
  Slides→`.pptx`, Drawings→`.png`, others→PDF).

## Files

| Path | Purpose |
|------|---------|
| `gdrive_du/auth.py` | OAuth desktop flow + Drive service |
| `gdrive_du/crawler.py` | Drive listing, tree building, size aggregation |
| `gdrive_du/render.py` | `du` / `tree` / human-readable size formatting |
| `gdrive_du/cli.py` | Command-line interface |
| `gdrive_du/web.py` | Flask backend |
| `templates/index.html` | Web UI (single page) |

## Notes / limits

- `credentials.json` and `token.json` are secrets — do not commit them.
- Very large drives (100k+ items) take a while to fetch; the crawl paginates 1000 items/request.
- Sizes reflect stored bytes, not "storage used" with any admin-level dedup.
