[← Netra Translate](../README.md)

# Configuration

The server reads these environment variables. In Docker, pass them with `-e`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `NETRA_HOST`, `NETRA_PORT` | `127.0.0.1`, `8000` | Where `netra-translate serve` listens (the Docker image uses `0.0.0.0`) |
| `NETRA_DATA_DIR` | `~/.cache/netra-translate/jobs` (`/data` in Docker) | Where jobs are stored |
| `NETRA_JOB_TTL_HOURS` | `24` | Delete documents this long after their last change |
| `NETRA_MAX_UPLOAD_MB`, `NETRA_MAX_PAGES` | `50`, `100` | Upload limits |
| `NETRA_API_KEY` | none | Require `X-API-Key` (or `Authorization: Bearer`) on `/v1/*` |
| `NETRA_LAYOUT` | `0` | Layout analysis on by default |
| `NETRA_DEVICE`, `NETRA_DETECTOR` | auto, `yolo` | Model device and text-line detector |
| `NETRA_WARMUP` | `1` | Load the models at start-up, so the first upload isn't slow |
| `NETRA_SYNC_TIMEOUT` | `120` | Seconds `wait=true` waits before answering 202 |
| `NETRA_DEMO` | `0` | Shared public server: never list jobs, and show a demo notice (used by the Hugging Face Space) |
| `NETRA_EMBEDDED_WORKER` | `1` | Run a worker inside `serve`; `0` is the same as `serve --no-worker` |
| `NETRA_THREADS` | `0` (all cores) | torch CPU threads per worker |

`serve` and `worker` also take `--config FILE`: the `server:` section of a YAML or JSON file sets these options by their lower-case names (`max_pages`, `job_ttl_hours`, …; see [examples/config.yaml](../examples/config.yaml)). Order of precedence: flags, then the file, then the environment, then the defaults. An unknown option is an error.

Without `NETRA_API_KEY`, anyone who can reach the port can use the server. Set the key, or put the server behind a proxy, before exposing it beyond your machine.
