# Homebrew cask

[`open-cad-studio.rb`](open-cad-studio.rb) is a [Homebrew Cask](https://docs.brew.sh/Cask-Cookbook)
for installing the macOS (Apple Silicon) build.

## Install without a tap (directly from this file)

```bash
brew install --cask --no-quarantine \
  https://raw.githubusercontent.com/HakanSeven12/OpenCADStudio/main/packaging/homebrew/open-cad-studio.rb
```

`--no-quarantine` is required: the app is ad-hoc signed but **not** Apple-notarised
(notarisation needs a paid Apple Developer ID), so without it Gatekeeper still
blocks the first launch.

## Publishing as a proper tap (recommended)

Create a separate GitHub repo named `homebrew-tap` under the same account, put a
copy of `open-cad-studio.rb` in its `Casks/` directory, then users can run:

```bash
brew install --cask --no-quarantine hakanseven12/tap/open-cad-studio
```

`brew upgrade` then keeps the app current automatically.

## Updating for a new release

Each release run prints the new `version` + `sha256` in the GitHub Actions job
summary (the **Emit Homebrew cask sha256** step). Paste those two lines into the
cask. To compute the digest manually:

```bash
shasum -a 256 OpenCADStudio-vX.Y.Z-macos-arm64.dmg
```
