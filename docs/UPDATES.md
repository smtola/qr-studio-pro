# In-app updates

Users never have to uninstall. **Help ▸ Check for Updates…** (and an automatic check at most once a day, switchable under
Help) compares the running version (shown in the window title, status bar and About box) with a small feed file.

## How it works
1. You publish a new build plus `update.json` (the feed) on any HTTPS host, e.g. GitHub Releases.
2. The app downloads `update.json`. If its `version` is newer, a dialog shows the release notes: **Update now / Later / Skip this version**.
3. *Update now* downloads the installer for this computer, checks its **SHA-256** against the feed (a mismatch is discarded), asks to save unsaved work, then:
   - **Windows:** runs `QRStudioPro-<ver>-Setup.exe /SILENT` over the existing install. The installer keeps the same `AppId`, so it **upgrades in place** (settings, presets and recent projects are untouched), closes the old app and starts the new one.
   - **macOS:** opens the new `.dmg`; the user drags the app onto Applications and chooses Replace. (Fully silent replacement on macOS needs a signed, notarized app and an updater framework such as Sparkle.)
4. Privacy: only an HTTPS GET of `update.json` is made; nothing about the user, their content or logos is sent.

## One-time setup
Set the feed address in `src/version.py` **before building**:
```python
UPDATE_MANIFEST_URL = "https://github.com/<you>/<repo>/releases/latest/download/update.json"
```
(`QRSP_UPDATE_URL` overrides it at run time, useful for testing.) Builds with an empty address simply say that update checking is not set up.
**Users must install a build that already contains this feature once**; every later version then arrives through the app.

## Releasing version 1.1.0
```bash
# 1. edit VERSION in src/version.py  ->  "1.1.0"
# 2. build on each OS (scripts/build_windows.ps1, scripts/build_macos.sh)
# 3. generate the feed from the installers in dist/ (run on the machine(s) holding them; --merge combines OSes)
python scripts/make_update_manifest.py --base-url https://github.com/<you>/<repo>/releases/download/v1.1.0 \
       --notes "What changed" --merge
# 4. upload the installers and dist/update.json to the release; make sure UPDATE_MANIFEST_URL resolves to update.json
```
Publish `update.json` last: users see the update only once the feed points at it. To withdraw a release, republish the previous feed.

## Security notes
- Only `https://` addresses are accepted; assets without a valid SHA-256 are ignored; file names must be `*.exe`/`*.dmg`; size limits apply.
- The checksum protects against corrupted or swapped downloads from the file host, **not** against someone who controls the feed itself. Host the feed on an account only you control, and code-sign the installers (see PACKAGING.md) so Windows/macOS verify the publisher too.
