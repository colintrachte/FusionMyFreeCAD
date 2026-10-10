# Package and upload a FusionMyFreeCAD release

This guide is the short operational path for producing a release archive and uploading it as a
reviewable GitHub draft. [RELEASING.md](../../RELEASING.md) remains the authoritative full runbook.

## 1. Obtain approval for the release version

Do not change FusionMyFreeCAD's main project version without the user's explicit prior approval.
Preparing, packaging, or uploading a release does not by itself authorize a version increment.

After approval, start from `main` with all intended changes committed or safely set aside. Confirm
that `git status --short` contains no unexpected work.

## 2. Prepare the approved version

From the repository root, replace `<version>` with the approved `X.Y.Z` value:

```powershell
python tools/prepare_release.py <version>
```

The preparation script updates the package and Ribbon layout versions, release date, download
references, and changelog. It also creates
`docs/release-notes/RELEASE-NOTES-<version>.md`.

Review every changed file. Replace every `TODO` in the changelog and release notes with final
plain-language content before continuing.

## 3. Validate and package locally

Install the pinned tools once:

```powershell
python -m pip install -r requirements-dev.txt
```

Run the same core checks used by CI and the release workflow:

```powershell
ruff check .
ruff format --check .
ruff check --isolated --select F821 --exclude '*.pyi' --exclude '*_ui.py' bundled-addons/
python -m pytest tests -q
python tools/build_addon_package.py
```

The package builder reads the version from `package.xml` and creates deterministic files under
`dist/`:

```text
dist/FusionMyFreeCAD-<version>.zip
dist/FusionMyFreeCAD-<version>.zip.sha256
```

Do not commit `dist/`; it is reproducible build output and is ignored by Git.

Inspect the archive before upload. It must have one top-level `FusionMyFreeCAD` folder containing
`InitGui.py`, `package.xml`, `Resources/`, and `bundled-addons/`. Verify the checksum and complete
the interactive FreeCAD checklist in [MAINTAINING.md](../../MAINTAINING.md) using a disposable or
backed-up profile.

## 4. Commit and push the release candidate

Review the exact release diff:

```powershell
git diff --check
git status --short
```

Commit with the approved version in the message, then push `main`. Do not push or publish unless the
user has explicitly authorized the remote operation.

## 5. Build and upload the GitHub draft

The supported upload path is `.github/workflows/release.yml`; it rebuilds and verifies the archive
on GitHub rather than trusting the local ZIP.

1. Open the repository on GitHub.
2. Choose **Actions → Build and upload draft release → Run workflow**.
3. Select `main` and enter `<version>` without a leading `v`.
4. Run the workflow.
5. Open the completed run and follow its draft-release link.

The workflow rejects a non-`main` ref, a version that differs from `package.xml`, unfinished release
notes, lint or test failures, and invalid package contents. On success it creates tag
`v<version>`, uploads the ZIP and checksum, and leaves the GitHub release in **draft** state.

## 6. Review and publish

Download the draft assets once and verify:

- filenames and version;
- SHA-256 checksum;
- archive structure;
- release title and notes;
- clean installation and **Verify UI** results.

Publishing is a separate external action. Do not click **Publish release** without explicit user
authorization. Until publication, the draft and tag are not a public FusionMyFreeCAD release.

## Failure and rollback

- If validation fails, fix the source and rerun the complete local gate.
- If the GitHub workflow fails, correct the source or metadata, commit, push, and rerun it.
- If a draft is wrong, leave it unpublished. Deleting its draft release or tag is destructive and
  requires explicit authorization.
- Never overwrite assets belonging to an already published release. Prepare a new approved project
  version instead.

