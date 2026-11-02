# Cyber Resilience of AI Systems — Lab 1

## Project

**Direction:** Computer Vision

**Topic:** Robustness of handwritten digit recognition under input distortions.

**Goal:** Prepare a secure and reproducible environment for developing a machine learning system.

**Input:** 8x8 grayscale image of a handwritten digit.

**Output:** Predicted digit class from 0 to 9.

**Potential user:** Automated handwritten document recognition system.

## Dataset

**Name:** Optical Recognition of Handwritten Digits

**Original source:**
https://archive.ics.uci.edu/dataset/80/optical+recognition+of+handwritten+digits

**Used version:**
https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_digits.html

Dataset characteristics:

- Original subset: 1797 images.
- Balanced subset: 1740 images.
- Classes: 10 (digits 0-9).
- Objects per class: exactly 174.
- Features: 64.
- Image dimensions: 8x8 pixels.
- Data type: numerical pixel intensities (0-16).

The balanced dataset was obtained using random undersampling without replacement, with random_state=42.

Both original and balanced datasets are preserved.

## Environment

- Ubuntu 24.04 LTS
- Python 3.12
- Git
- Docker and Docker Compose
- JupyterLab
- SSH with ED25519 keys
- UFW firewall

## Installation

Clone the repository and open the project directory.

Create a Python virtual environment:

    python3 -m venv .venv

Activate it:

    source .venv/bin/activate

Install the dependencies:

    python -m pip install -r requirements.txt

## Run the Analysis

Start JupyterLab:

    jupyter lab --no-browser --ip=127.0.0.1 --port=8888

Open:

    notebooks/01_digits_analysis.ipynb

Run all notebook cells.

## Data Integrity

Verify the dataset files:

    sha256sum -c integrity/datasets.sha256

Both files should return OK.

The reference hashes should be stored separately from the editable data for independent verification.

## Dependency Audit

Run:

    pip-audit

The initial audit found no known vulnerabilities in the installed Python dependencies.

## Project Structure

- data/ - Original and balanced datasets
- notebooks/ - Jupyter notebooks
- src/ - Source code
- models/ - Trained models
- tests/ - Automated tests
- reports/ - Analysis and security results
- integrity/ - SHA256 manifests
- requirements.txt - Python dependencies
- .gitignore - Excluded files

## Security

Development is performed using the non-root user mluser.

SSH key authentication, root login restrictions, UFW rules and dependency auditing have been configured.

The project includes SHA256 integrity verification and a threat model.

Secrets and private SSH keys must never be committed to Git.

## Future Work

Lab 2 will train a baseline digit classification model.

Further experiments will investigate the robustness of the model against corrupted and adversarial inputs.
