# Protein Language Model Evaluation Framework

A framework for training and evaluating models that predict protein properties based on embeddings generated by different Protein Language Models (PLMs).

## Features

*   Modular structure separating data loading, model definition, training, and evaluation.
*   Configuration management via `src/unknown_unknowns/configs/config.py`.
*   Uses `uv` for dependency management.
*   Separate scripts for training and evaluation.
*   TensorBoard logging for experiment tracking.

## Setup

1.  **Prerequisites:**
    *   Python >= 3.12
    *   `uv` installed (`pip install uv`)

2.  **Create Environment & Install Dependencies:**
    ```bash
    # Create a virtual environment (optional but recommended)
    uv venv
    source .venv/bin/activate

    # Install dependencies
    uv pip install -r requirements.txt # Or directly: uv pip install .[dev]
    ```
    *(Note: Ensure a `requirements.txt` or appropriate install targets exist in `pyproject.toml`)*

3.  **Data:**
    *   Place your training/validation/test CSV files in subdirectories within `data/swissprot/` (e.g., `data/swissprot/training/`, `data/swissprot/train_sub/`).
    *   Place your HDF5 embedding file (e.g., `prott5.h5`) in `data/swissprot/embeddings/`.
    *   Update data paths in `src/unknown_unknowns/configs/config.py` if necessary.

## Usage

1.  **Configuration:** Modify default parameters, paths, etc., in `src/unknown_unknowns/configs/config.py`.

2.  **Training:**
    ```bash
    # Example: Train using the 'training' dataset split
    python src/unknown_unknowns/train.py --csv_subdir training

    # Example: Train using the 'train_sub' dataset split
    python src/unknown_unknowns/train.py --csv_subdir train_sub
    ```
    *   Checkpoints and logs will be saved in `models/runs/[TIMESTAMP]/`.

3.  **Evaluation:**
    ```bash
    # Evaluate the best checkpoint from a specific run directory
    python src/unknown_unknowns/evaluate.py --run_dir models/runs/[TIMESTAMP]

    # Evaluate using a specific test set (optional)
    python src/unknown_unknowns/evaluate.py --run_dir models/runs/[TIMESTAMP] --test_csv path/to/your/custom_test.csv
    ```
    *   Evaluation results (plots, metrics) will be saved in `models/runs/[TIMESTAMP]/evaluation_results/`.

4.  **Monitoring (TensorBoard):**
    ```bash
    tensorboard --logdir models/runs/[TIMESTAMP]/tensorboard
    ```
    Or view logs across all runs:
    ```bash
    tensorboard --logdir models/runs
    ```

## Project Structure

```
.
├── data/                   # Data files (CSVs, embeddings)
│   └── swissprot/
│       ├── embeddings/
│       └── [training|train_sub|...]/ # CSV splits
├── models/
│   └── runs/               # Output directory for training runs (logs, checkpoints)
│       └── [TIMESTAMP]/    # Individual run directory
│           ├── checkpoints/
│           ├── tensorboard/
│           └── evaluation_results/ # Added by evaluate.py
├── notebooks/              # Jupyter notebooks
├── src/
│   └── unknown_unknowns/   # Main source code package
│       ├── configs/
│       ├── data/
│       ├── evaluation/
│       ├── models/
│       ├── utils/
│       └── visualization/
│       ├── train.py        # Training script
│       └── evaluate.py     # Evaluation script
├── .gitignore
├── .python-version
├── pyproject.toml          # Project metadata and dependencies
├── README.md
└── uv.lock                 # uv lock file
```
