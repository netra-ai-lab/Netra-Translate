[← Netra Translate](../README.md)

# Development

## Tests

```bash
pip install -e ".[server,dev]" && pytest      # the unit tests use fake models, so no weights are needed
```

## Releasing

Push a version tag (`git tag v1.0.0 && git push --tags`). [`.github/workflows/docker.yml`](../.github/workflows/docker.yml) then builds amd64 and arm64 images natively, runs the smoke test on both, and publishes `ghcr.io/netra-ai-lab/netra-translate:1.0.0`, `:1.0` and `:latest`. After that, bump the tag in [`deploy/hf-space/Dockerfile`](../deploy/hf-space/Dockerfile) and push that folder to the Space.

The first time a new image name is published, GHCR makes the package private. Make it public once under *Package settings → Danger Zone → Change visibility*, or `docker pull` fails for everyone else.

To build the image yourself, run `docker build -f docker/Dockerfile -t netra-translate .`. The build downloads every model and runs [a smoke test](../docker/smoke_test.py) against the real models.
