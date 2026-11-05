#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
mkdir -p reports/evidence metrics models reports/figures

# Never rewrite the reference hashes from Lab 1.
echo '=== Verification of frozen Lab 1 CSV hashes ==='
sha256sum -c integrity/datasets.sha256 | tee reports/evidence/lab2_data_sha256.txt

echo '=== Reproducible training and test metrics ==='
python -m src.train 2>&1 | tee reports/evidence/lab2_training.txt

echo '=== Image robustness experiment ==='
python -m src.robustness 2>&1 | tee reports/evidence/lab2_robustness.txt

echo '=== Input validation evidence with actual results ==='
python -m src.validation_cases 2>&1 | tee reports/evidence/lab2_validation_cases.txt

echo '=== Automated pytest suite ==='
python -m pytest tests/ -q 2>&1 | tee reports/evidence/lab2_pytest.txt

echo '=== Bandit static code security scan ==='
python -m bandit -r src/ 2>&1 | tee reports/evidence/lab2_bandit.txt

echo '=== Verify persisted model hash and loading ==='
sha256sum -c integrity/model.sha256 | tee reports/evidence/lab2_model_sha256.txt
python -m src.verify 2>&1 | tee reports/evidence/lab2_final_verification.txt

echo '=== Create private model delivery archive ==='
python -m src.package_model_private 2>&1 | tee reports/evidence/lab2_private_model_package.txt

echo '=== Record Python versions for reproduction ==='
python -m pip freeze > requirements.txt
python --version | tee reports/evidence/lab2_python_version.txt
printf 'Lab 2 completed. No tokens, keys or model files were copied into public directories.\n'
