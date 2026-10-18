# Hugging Face Space (Docker SDK): the released Netra Translate image, with demo limits.
# The Space runs the real app, not a separate demo UI. Bump the tag with each release.
FROM ghcr.io/netra-ai-lab/netra-translate:1.0.0

# Shared public server: show the demo notice, keep uploads small and delete them soon.
# Jobs are never listed (GET /v1/jobs is empty); each browser only sees the ids it
# created, and ids are unguessable, so visitors can't see each other's files.
ENV NETRA_DEMO=1 \
    NETRA_MAX_PAGES=5 \
    NETRA_MAX_UPLOAD_MB=10 \
    NETRA_JOB_TTL_HOURS=1
