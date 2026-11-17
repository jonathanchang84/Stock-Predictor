# Stock Predictor

## Build

```sh
npm ci
npm run tauri:build
```

The macOS application bundle is created under `src-tauri/target/release/bundle/macos/`.

## Publish a macOS release

Push a version tag such as `v0.1.0`. GitHub Actions builds the application and
publishes a `Stock-Predictor-macos.zip` asset to a GitHub Release for that tag.

