"""
This script trains a specified model or calculates the Euclidean baseline.

Usage:
python train.py --model_type fnn --embedding_file path/to/embeddings.h5 --csv_dir path/to/csv_dir --param_name param_name
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Tuple, Type
import yaml
import pytorch_lightning as pl
import torch
from pytorch_lightning.callbacks import EarlyStopping, ModelCheckpoint
from pytorch_lightning.loggers import TensorBoardLogger
from torch.utils.data import DataLoader

from src.shared.datasets import create_single_loader, get_embedding_size
from src.training.models import (
    FNNPredictor,
    LinearRegressionPredictor,
    LinearDistancePredictor,
)


# Define a simple structure to hold paths
@dataclass
class ResolvedPaths:
    project_root: Path
    embeddings_file: Path  # Absolute path
    csv_dir: Path  # Absolute path
    train_csv: Path  # Absolute path
    val_csv: Path  # Absolute path
    test_csv: Path  # Absolute path
    output_dir: Path  # Base dir for the param/embedding combo
    run_dir: Path  # Timestamped run directory


def setup_environment(seed: int):
    """Set random seed and PyTorch settings."""
    pl.seed_everything(seed)
    if torch.cuda.is_available():
        print("CUDA available, setting matmul precision to medium.")
        torch.set_float32_matmul_precision("medium")
    else:
        print("CUDA not available.")


def prepare_paths(
    output_base_dir: Path,
    embeddings_file: Path,
    csv_dir: Path,
    project_root: Path,
) -> ResolvedPaths:
    """Resolve output paths based on provided absolute inputs and create run directory."""

    # Ensure provided paths exist
    if not embeddings_file.is_file():
        raise FileNotFoundError(f"Embeddings file not found: {embeddings_file}")
    if not csv_dir.is_dir():
        raise NotADirectoryError(f"CSV directory not found: {csv_dir}")

    # Create timestamped run directory within the provided base experiment dir
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_base_dir.resolve() / timestamp
    print(f"Creating run directory: {run_dir}")

    # Create run structure
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run_dir / "tensorboard").mkdir(parents=True, exist_ok=True)

    # Resolve absolute paths for CSV files within the provided csv_dir
    train_csv = (csv_dir / "train.csv").resolve()
    val_csv = (csv_dir / "val.csv").resolve()
    test_csv = (csv_dir / "test.csv").resolve()

    # Check essential CSV files exist
    if not train_csv.is_file():
        raise FileNotFoundError(f"Train CSV not found: {train_csv}")
    if not val_csv.is_file():
        raise FileNotFoundError(f"Validation CSV not found: {val_csv}")
    if not test_csv.is_file():
        print(f"Warning: Test CSV not found: {test_csv}")

    return ResolvedPaths(
        project_root=project_root,
        embeddings_file=embeddings_file,
        csv_dir=csv_dir,
        train_csv=train_csv,
        val_csv=val_csv,
        test_csv=test_csv,
        output_dir=output_base_dir.resolve(),
        run_dir=run_dir,
    )


def prepare_data(
    param_name: str,
    batch_size: int,
    embeddings_file: Path,
    train_csv: Path,
    val_csv: Path,
    num_workers: int,
) -> Tuple[int, DataLoader, DataLoader]:
    """Load train/val datasets and return embedding size and dataloaders."""
    print("Preparing train and validation data loaders...")
    embedding_size = get_embedding_size(str(embeddings_file))
    print(f"Detected embedding size: {embedding_size}")

    loader_args = {
        "hdf_file": str(embeddings_file),
        "param_name": param_name,
        "batch_size": batch_size,
        "num_workers": num_workers,
    }
    print(f"Using {num_workers} worker(s) for DataLoaders.")

    train_loader = create_single_loader(
        csv_file=str(train_csv), shuffle=True, **loader_args
    )
    val_loader = create_single_loader(
        csv_file=str(val_csv), shuffle=False, **loader_args
    )

    print(f"Train batches: {len(train_loader)}, Val batches: {len(val_loader)}")
    return embedding_size, train_loader, val_loader


def train_model(
    model_class: Type[pl.LightningModule],
    model_kwargs: dict,
    trainer_kwargs: dict,
    paths: ResolvedPaths,
    train_loader: DataLoader,
    val_loader: DataLoader,
    early_stopping_patience: int,
    hparams_log: dict,
) -> Tuple[str, TensorBoardLogger]:
    """Configure and run the PyTorch Lightning training loop for a given model."""
    print(f"Configuring model ({model_class.__name__}) and trainer...")

    # Instantiate the selected model
    model = model_class(**model_kwargs)

    # Callbacks
    checkpoint_callback = ModelCheckpoint(
        dirpath=paths.run_dir / "checkpoints",
        save_top_k=1,
        monitor="val_loss",
        mode="min",
        filename="model-{epoch:02d}-{val_loss:.3f}",
    )
    early_stopping_callback = EarlyStopping(
        monitor="val_loss",
        patience=early_stopping_patience,
        mode="min",
        verbose=True,
    )
    callbacks = [early_stopping_callback, checkpoint_callback]

    # Logger
    logger = TensorBoardLogger(
        save_dir=str(paths.run_dir / "tensorboard"),
        name=None,
        version="",
        default_hp_metric=False,
    )

    # Log hyperparameters manually
    logger.log_hyperparams(hparams_log)

    # --- Trainer Setup ---
    logging_steps = max(1, len(train_loader) // 4)
    trainer = pl.Trainer(
        callbacks=callbacks,
        logger=logger,
        log_every_n_steps=logging_steps,
        enable_checkpointing=True,
        enable_progress_bar=False,
        enable_model_summary=True,
        **trainer_kwargs,
    )

    # --- Training ---
    print("Starting training...")
    trainer.fit(model, train_loader, val_loader)

    best_model_path = checkpoint_callback.best_model_path
    print(f"\nTraining finished. Best model saved at: {best_model_path}")

    return best_model_path, logger


def main(args):
    """Main workflow orchestrator for training or Euclidean baseline setup."""
    setup_environment(args.seed)

    project_root = Path(__file__).parent.parent.parent

    paths = prepare_paths(
        output_base_dir=args.output_base_dir,
        embeddings_file=args.embedding_file,
        csv_dir=args.csv_dir,
        project_root=project_root,
    )

    # --- Euclidean Baseline Setup Only ---
    if args.model_type == "euclidean":
        print("Setting up run directory for Euclidean Distance Baseline...")

        # Need embedding size for hparams
        try:
            embedding_size = get_embedding_size(str(paths.embeddings_file))
        except Exception as e:
            print(f"Error getting embedding size for hparams: {e}")
            embedding_size = -1  # Indicate error or unknown

        # Save hparams for evaluation script consistency
        hparams_to_log = {
            "model_type": args.model_type,
            "param_name": args.param_name,
            "embedding_file": str(paths.embeddings_file),
            "csv_dir": str(paths.csv_dir),
            "embedding_size": embedding_size,
            "batch_size": args.batch_size,  # Log batch size potentially used by eval
            "seed": args.seed,
        }
        hparams_path = paths.run_dir / "tensorboard" / "hparams.yaml"
        try:
            hparams_path.parent.mkdir(
                parents=True, exist_ok=True
            )  # Ensure tensorboard dir exists
            with open(hparams_path, "w") as f:
                yaml.dump(hparams_to_log, f)
            print(f"Saved hyperparameters to {hparams_path}")
        except Exception as e:
            print(f"Error saving hyperparameters: {e}")

        print("\nEuclidean baseline setup complete.")
        print(f"Run directory created: {paths.run_dir}")
        # Print the run dir path for the runner script
        print(str(paths.run_dir.resolve()))

    # --- Standard Model Training ---
    else:
        embedding_size, train_loader, val_loader = prepare_data(
            param_name=args.param_name,
            batch_size=args.batch_size,
            embeddings_file=paths.embeddings_file,
            train_csv=paths.train_csv,
            val_csv=paths.val_csv,
            num_workers=args.num_workers,
        )

        # Prepare model arguments
        model_kwargs = {
            "embedding_size": embedding_size,
            "learning_rate": args.learning_rate,
        }
        if args.model_type == "fnn":
            model_class = FNNPredictor
            model_kwargs["hidden_size"] = args.hidden_size
        elif args.model_type == "linear":
            model_class = LinearRegressionPredictor
        elif args.model_type == "linear_distance":
            model_class = LinearDistancePredictor
        else:
            raise ValueError(f"Unknown trainable model_type: {args.model_type}")

        # Prepare trainer arguments
        trainer_kwargs = {
            "max_epochs": args.max_epochs,
            "accelerator": "auto",
            "devices": "auto",
        }

        # Prepare hyperparameters to log (subset of args + derived)
        hparams_to_log = {
            "model_type": args.model_type,
            "param_name": args.param_name,
            "embedding_file": str(paths.embeddings_file),
            "csv_dir": str(paths.csv_dir),
            "embedding_size": embedding_size,
            "learning_rate": args.learning_rate,
            "batch_size": args.batch_size,
            "max_epochs": args.max_epochs,
            "early_stopping_patience": args.early_stopping_patience,
            "seed": args.seed,
        }
        if args.model_type == "fnn":
            hparams_to_log["hidden_size"] = args.hidden_size

        # Train model
        best_model_path, _ = train_model(
            model_class=model_class,
            model_kwargs=model_kwargs,
            trainer_kwargs=trainer_kwargs,
            paths=paths,
            train_loader=train_loader,
            val_loader=val_loader,
            early_stopping_patience=args.early_stopping_patience,
            hparams_log=hparams_to_log,
        )

        # --- Final Output for Training ---
        print(
            f"\nRun completed successfully. Best checkpoint saved to: {best_model_path}"
        )
        print("To view TensorBoard logs for this run, use:")
        print(f"tensorboard --logdir {paths.run_dir / 'tensorboard'}")
        print("\nTo evaluate the best model, run evaluate.py using the run directory:")
        print(
            f'uv run python src/unknown_unknowns/evaluate.py --run_dir "{paths.run_dir}"'
        )
        # Print the run dir path for the runner script
        print(str(paths.run_dir.resolve()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train a specified model or calculate Euclidean baseline."
    )

    # --- Model Selection ---
    parser.add_argument(
        "--model_type",
        type=str,
        required=True,
        choices=["fnn", "linear", "euclidean", "linear_distance"],
        help="Type of model to train or baseline to set up.",
    )

    # --- Input Data Paths ---
    parser.add_argument(
        "--embedding_file",
        type=Path,
        required=True,
        help="Absolute path to the embedding HDF5 file.",
    )
    parser.add_argument(
        "--csv_dir",
        type=Path,
        required=True,
        help="Absolute path to the directory containing train.csv, val.csv, test.csv.",
    )
    parser.add_argument(
        "--param_name",
        type=str,
        required=True,
        choices=["fident", "alntmscore", "hfsp"],
        help="Target parameter name to train the model for.",
    )

    # --- Output Location ---
    parser.add_argument(
        "--output_base_dir",
        type=Path,
        required=True,
        help="Absolute path to the base directory where the timestamped run folder should be created.",
    )

    # --- Core Training Hyperparameters (with defaults set here) ---
    parser.add_argument(
        "--learning_rate",
        type=float,
        default=0.001,
        help="Learning rate (default: 0.001)",
    )
    parser.add_argument(
        "--batch_size", type=int, default=1024, help="Batch size (default: 1024)"
    )
    parser.add_argument(
        "--max_epochs",
        type=int,
        default=100,
        help="Maximum number of training epochs (default: 100)",
    )
    parser.add_argument(
        "--early_stopping_patience",
        type=int,
        default=5,
        help="Patience for early stopping (default: 5)",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed (default: 42)"
    )
    parser.add_argument(
        "--num_workers",
        type=int,
        default=4,
        help="Number of DataLoader workers (default: 4)",
    )

    # --- Model Specific Hyperparameters ---
    # Only relevant for FNN
    parser.add_argument(
        "--hidden_size",
        type=int,
        default=64,
        help="Hidden layer size for FNN model (default: 64) - Ignored for linear model.",
    )

    args = parser.parse_args()

    main(args)
