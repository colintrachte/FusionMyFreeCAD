# Make a new FusionMyFreeCAD release

This is the maintainer's start-to-finish release runbook. The preparation command updates the
version everywhere it belongs. GitHub then repeats all automated checks, builds the archive, and
uploads a **draft** release. Nothing becomes public until you review the draft and click
**Publish release**.

## One-time setup

1. Install Python 3.11 or newer and Git.
2. Clone the repository and open a terminal in its top-level folder.
3. Install the pinned release tools:

   ```powershell
   python -m pip install -r requirements-dev.txt
   ```

4. On GitHub, open **Settings → Actions → General**. Under **Workflow permissions**, allow GitHub
   Actions to create releases. Repository or organization policy may already provide this.

## 1. Prepare the release

Start from `main` after all intended changes are committed or safely set aside. Confirm
`git status --short` shows no unexpected files, then run:

```powershell
python tools/prepare_release.py 1.3.0
```

Replace `1.3.0` with the new version. The command updates `package.xml`, both Ribbon layout
versions, the current download links, and the release date. It also creates:

- a new section at the top of `CHANGELOG.md`;
- `docs/RELEASE-NOTES-1.3.0.md` for the text shown on GitHub.

Open those two files and replace every `TODO` with plain-language changes, fixes, and any upgrade
warning. Do not move old release notes into the new file; they remain historical records.

## 2. Validate the exact release candidate

Run the automated checks and build locally:

```powershell
ruff check .
ruff format --check .
python -m pytest tests -q
python tools/build_addon_package.py
```

The last command creates these ignored files under `dist/`:

- `FusionMyFreeCAD-1.3.0.zip`
- `FusionMyFreeCAD-1.3.0.zip.sha256`

Complete the **Interactive FreeCAD checklist** in `MAINTAINING.md`. Use a disposable or backed-up
FreeCAD profile. Automated tests do not validate the real FreeCAD UI or production CAD output.

Inspect the ZIP before continuing. It must contain one top-level `FusionMyFreeCAD` folder, with
`InitGui.py`, `package.xml`, `Resources`, and `bundled-addons` directly inside it.

## 3. Commit and push

Review the diff, then commit and push the prepared release candidate:

```powershell
git diff --check
git status --short
git add package.xml README.md CHANGELOG.md docs/INSTALL-FREECAD-ADDON.md docs/RELEASE-NOTES-1.3.0.md Resources/FusionMyFreeCAD/layout-v3.json Resources/FusionMyFreeCAD/layout-manifest.json
git commit -m "Prepare FusionMyFreeCAD 1.3.0"
git push origin main
```

Use your actual version in the filename and message. Do not add `dist/`; GitHub builds fresh files
from the committed source.

## 4. Build and upload on GitHub

1. Open the repository on GitHub.
2. Choose **Actions → Build and upload draft release → Run workflow**.
3. Leave the branch set to `main`, enter the version without `v` (for example `1.3.0`), and run it.
4. Open the completed run. Its summary links to the draft release.
5. Download the ZIP and checksum once, and inspect the release notes and filename.
6. Click **Edit**, then **Publish release** when everything is correct.

The workflow refuses to release from another branch, a mismatched version, missing or unfinished
release notes, failed lint/format/tests, or an invalid archive. It creates tag `v1.3.0` at the exact
commit it built and uploads both release files.

## If something fails

- **A check fails:** fix the source, rerun the local checks, commit, push, and start the workflow
  again.
- **The workflow cannot create the release:** confirm **Settings → Actions → General → Workflow
  permissions** permits write access.
- **A draft was created but needs changes:** leave it unpublished while you correct the source.
  Delete that draft and its tag in GitHub before rerunning the same version. Deleting published
  releases or tags is a deliberate maintainer action; never overwrite a public release asset.
- **The version is wrong:** do not edit generated ZIP filenames. Correct the committed metadata by
  rerunning `prepare_release.py` with the intended version, then rebuild.
