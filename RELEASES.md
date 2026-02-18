# Release System

This project ships automated cross-platform release builds from Git tags.

## Output Targets

Each tagged release (`v*`) produces:

- Linux:
  - Portable: `Datamosh-<version>-linux-portable.tar.gz`
  - Installer: `Datamosh-<version>-linux-installer.deb`
  - AppImage: `Datamosh-<version>-linux-<arch>.AppImage`
- Windows:
  - Portable: `Datamosh-<version>-windows-portable.zip`
  - Installer: `Datamosh-<version>-windows-installer.exe`
- macOS:
  - Portable: `Datamosh-<version>-macos-portable.zip`
  - Installer: `Datamosh-<version>-macos-installer.dmg`

Checksums are included as `SHA256SUMS-*.txt`.

## How to Publish

1. Update `VERSION` in the repository if needed.
2. Commit changes to `main`.
3. Create and push a tag:

```bash
git tag -a v1.1.0-beta.4 -m "Beta 4 release"
git push origin v1.1.0-beta.4
```

4. GitHub Actions workflow `.github/workflows/release.yml` builds all artifacts and publishes them to the GitHub Release.

## Prerelease Behavior

- Tags containing a hyphen (for example `v1.2.0-beta.1`) are published as prereleases.
- Normal semantic tags (for example `v1.2.0`) are published as stable releases.

## Update System

The app includes a **Check for Updates** action in the toolbar.

- It queries GitHub Releases for `willbearfruits/datamosh-gui`.
- Stable builds track stable releases.
- Prerelease builds track prerelease channel updates.
- When a newer version is found, it opens the best platform-specific download link.
