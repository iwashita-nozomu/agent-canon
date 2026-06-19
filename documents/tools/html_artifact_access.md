<!--
@dependency-start
contract reference
responsibility Documents local-browser access for remote HTML artifacts.
upstream design ../result-log-retention-and-visualization.md defines visual artifact retention.
upstream design ../experiment-report-style.md defines experiment report artifact layout.
upstream design ../server-host-contract.md defines SSH/HPC/container host assumptions.
upstream implementation ../../tools/experiments/html_artifact_access.py prints access commands.
upstream design ../../tools/catalog.yaml catalogs the helper.
downstream implementation ../../tests/tools/test_html_artifact_access.py covers command rendering.
@dependency-end
-->

# HTML Artifact Access

`tools/experiments/html_artifact_access.py` prints the `python3 -m http.server`
and SSH tunnel commands needed to view a remote HTML report in the browser on
the local PC. It is intended for the common chain:

```text
local PC browser -> SSH tunnel -> HPC host -> container or remote workspace
```

The helper prints commands; it does not open a browser by itself. The default
bind address is `127.0.0.1`. Container-direct mode uses `0.0.0.0` inside the
container so the SSH host can reach the container IP.

## Direct Python Server Mode

Use this when the HTML file is visible from the shell where the helper runs.

```bash
python3 tools/experiments/html_artifact_access.py \
  experiments/<topic>/result/<run-id>/report.html
```

Run `HTML_ARTIFACT_SERVER_COMMAND` on the HPC shell where the file exists. On
the local PC, run `HTML_ARTIFACT_TUNNEL_COMMAND`, then open
`HTML_ARTIFACT_LOCAL_URL`. The helper uses `AGENT_CANON_SSH_HOST` first, then
`SSH_CONNECTION`, to infer the SSH target. If neither is available, the tunnel
command contains `<ssh-host>` as the only field to replace.

## Container Direct Mode

Use this when the file is inside the current container on the HPC host. The
helper uses the current runtime's non-loopback IPv4 address as the SSH tunnel
target and binds the Python server to `0.0.0.0` inside the container.

```bash
python3 tools/experiments/html_artifact_access.py \
  /workspace/experiments/<topic>/result/<run-id>/report.html \
  --use-container-ip
```

Run the printed commands in this order:

1. `HTML_ARTIFACT_SERVER_COMMAND` inside the container where the file exists.
1. `HTML_ARTIFACT_TUNNEL_COMMAND` on the local PC.
1. Open `HTML_ARTIFACT_LOCAL_URL` in the local browser.

If the container IP must be supplied manually, pass it as the tunnel target and
bind the server to all container interfaces.

```bash
python3 tools/experiments/html_artifact_access.py \
  /workspace/experiments/<topic>/result/<run-id>/report.html \
  --bind 0.0.0.0 \
  --tunnel-target <container-ip>
```

Use `--port` when the default port is already in use. Use a staging copy only as
a alternate route when the SSH host cannot route to the container IP.
