# Launch demo

This folder produces the public Alpicool launch media from two real inputs:

1. A live BLE state change recorded in a scripted terminal.
2. Recorded overnight temperature samples copied into the ignored local `data/` folder.

Record the terminal proof with `asciinema`, then render it locally with `agg` and `ffmpeg`:

```bash
./scripts/demo/record-live.sh
```

The live command captures the original power and target temperature, changes the target temporarily, confirms the device response, and restores and verifies the original state before it exits.

If the live recorder cannot complete reliably, first preserve the three real responses as a sanitized JSON trace and render that trace without touching the cooler again:

```bash
./scripts/demo/record-trace.sh artifacts/demo/live-ble-trace.json
```

The rendered sequence must say `Recorded BLE session`; it must not present a replay as a live connection.

Render the combined MP4, GIF, poster and chart:

```bash
./scripts/demo/render-demo.sh
```

Generated media stays under the ignored `artifacts/` folder until it has been reviewed. Copy only approved final assets into the website repository.
