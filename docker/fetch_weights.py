"""Download every model the app needs into the Hugging Face cache (HF_HOME).

Run at image build time so the container works offline (HF_HUB_OFFLINE=1).
Same as `netra-translate download --layout`.
"""

from netra_translate.models import download

download(layout=True)
