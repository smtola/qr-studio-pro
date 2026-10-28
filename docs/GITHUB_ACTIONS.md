# Build and release with GitHub Actions

`.github/workflows/build.yml` builds Windows (installer + portable), macOS Apple Silicon and macOS Intel on GitHub's own machines,
then publishes a GitHub Release containing the installers and `update.json`. See the step-by-step in the project README / chat.

* Push a tag `vX.Y.Z` (must equal `VERSION` in `src/version.py`) -> build + publish release.
* *Actions > build-and-release > Run workflow* -> build only (download the files from the run's *Artifacts*).
* The repository must be **public** for the in-app updater to download `update.json` and the installers without a login.
* Release notes: edit `RELEASE_NOTES.md` before tagging; they appear in the app's update dialog.
* Builds are not code-signed (see PACKAGING.md).
