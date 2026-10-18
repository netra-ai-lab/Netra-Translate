[← Netra Translate](../README.md)

# Scaling

By default `netra-translate serve` is one process: the API plus one worker that runs jobs one at a time. To run several jobs at once, start the API without a worker and add worker processes on the same data directory:

```bash
netra-translate serve --no-worker --data-dir /srv/netra
netra-translate worker --data-dir /srv/netra --threads 2      # start as many as fit
netra-translate worker --data-dir /srv/netra --threads 2
```

With Docker Compose:

```bash
docker compose -f docker-compose.yml -f docker-compose.scale.yml up --build --scale worker=3
```

- **The data directory is the queue.** Uploads are queued as files, and a worker claims one with an atomic rename, so a job runs only once whichever worker is free. The order is upload order. The directory must be a local disk or a volume where rename is atomic; a network share that doesn't guarantee that isn't supported.
- **Each worker loads its own models**, so memory grows with every worker. The API process loads none. Measured on native Windows (CPU, one-page scan, no layout model): API process 317 MB; each worker about 0.83 GB, peaking at 0.98 GB during a job. Set `--threads` (`NETRA_THREADS`) so that workers × threads doesn't exceed the CPU cores.
- **Workers come and go.** A worker writes a heartbeat every 5 seconds. One that stops for 30 seconds is considered gone, and its job is marked failed with a message to retry. `SIGTERM` (or Ctrl+C) lets the worker finish its current job first; a second one stops it at once. Jobs still queued wait for the next worker, and survive restarts.
- **`GET /ready`** returns 503 until a worker has loaded its models; use it as a load-balancer or Kubernetes readiness check. The nav bar shows the number of workers, and *Waiting for a worker…* when there are none.
- Give workers the same `NETRA_MAX_PAGES` as the API. On a worker, `NETRA_LAYOUT=1` only means it loads the layout model at start-up; each job carries its own layout choice.
