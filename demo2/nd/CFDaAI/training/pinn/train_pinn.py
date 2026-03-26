#!/usr/bin/env python3
"""
Simplified training wrapper for pipeline integration.
Handles CSV file discovery and passes to MPWB2_CFD.
Usage: python3 train_cfd.py <csv_directory> <model_name> [options]
"""

import sys
import os
import glob
import json
import argparse
import time
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MPWB2_CFD import main as train_main


def find_cfd_csv_files(directory):
    """Find all CFD CSV files in directory."""
    # Support both naming conventions:
    #   Old: cups_structure_ws<N>_*.csv
    #   New: sim_<N>_ws_<X.XX>_wd_<Y>.csv
    csv_files = glob.glob(os.path.join(directory, 'cups_structure_ws*.csv'))
    csv_files += glob.glob(os.path.join(directory, 'sim_*_ws_*.csv'))
    return sorted(set(csv_files))


def validate_input(csv_dir):
    """Validate input directory and CSV files."""
    if not os.path.isdir(csv_dir):
        raise ValueError(f"Input directory not found: {csv_dir}")
    
    csv_files = find_cfd_csv_files(csv_dir)
    if not csv_files:
        raise ValueError(f"No CFD CSV files found in {csv_dir} (tried cups_structure_ws*.csv and sim_*_ws_*.csv)")
    
    return csv_files


def create_training_summary(experiment_dir, model_name="cfd_model"):
    """Create summary of training results."""
    summary = {
        'model_dir': experiment_dir,
        'weights': os.path.join(experiment_dir, f'{model_name}.weights.h5'),
        'normalization': os.path.join(experiment_dir, f'{model_name}.normalization.json'),
        'model_meta': os.path.join(experiment_dir, f'{model_name}.model_meta.json'),
        'config': os.path.join(experiment_dir, f'{model_name}.run.json'),
        'log': os.path.join(experiment_dir, 'training.log')
    }
    
    # Verify files exist
    missing_files = []
    for key in ['weights', 'normalization', 'model_meta']:
        if not os.path.exists(summary[key]):
            missing_files.append(key)
    
    if missing_files:
        print(f"WARNING: Missing expected files: {', '.join(missing_files)}")
    
    return summary


def main():
    parser = argparse.ArgumentParser(
        description='Train CFD PINN model from OpenFOAM simulation data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 train_cfd.py /path/to/simulations cfd_model --epochs 1000
  python3 train_cfd.py /path/to/simulations cfd_model --epochs 5000 --cpoints 5000
  python3 train_cfd.py /path/to/simulations cfd_model --learning_rate 0.0001
        """
    )
    
    parser.add_argument('csv_dir', help='Directory containing CFD CSV files (pattern: cups_structure_ws*.csv)')
    parser.add_argument('model_name', help='Model name prefix for saved weights and metadata')
    parser.add_argument('--epochs', type=int, default=100, help='Training epochs (default: 100)')
    parser.add_argument('--batch_size', type=int, default=512, help='Batch size (default: 512)')
    parser.add_argument('--cpoints', type=int, default=2000, help='Collocation points (default: 2000)')
    parser.add_argument('--learning_rate', type=float, default=2e-3, help='Initial learning rate (default: 2e-3, CosineDecay)')
    parser.add_argument('--patience', type=int, default=60, help='Early stopping patience (default: 60)')
    parser.add_argument('--alpha', type=float, default=0.07, help='Physics weight (default: 0.07 = 7%%)')
    parser.add_argument('--nu', type=float, default=0.01, help='Viscosity term (default: 0.01)')
    parser.add_argument('--w_div', type=float, default=1.0, help='Divergence weight (default: 1.0)')
    parser.add_argument('--test_size', type=float, default=0.2, help='Test fraction (default: 0.2)')
    parser.add_argument('--val_size', type=float, default=0.1, help='Validation fraction (default: 0.1)')
    parser.add_argument('--hidden', type=int, default=128, help='Hidden layer width (default: 128)')
    parser.add_argument('--n_layers', type=int, default=4, help='Residual blocks (default: 4)')
    parser.add_argument('--max_points_per_file', type=int, default=5000,
                        help='Max random points per wind-speed file (default: 5000)')
    parser.add_argument('--umag_min', type=float, default=0.10,
                        help='Drop stagnation points with |U| <= this (default: 0.10)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--init_weights', type=str, default=None, 
                        help='Path to pretrained weights for fine-tuning')
    parser.add_argument('--output_dir', type=str, default=None,
                        help='Output directory for model and logs (default: experiment_cfd_<timestamp>)')
    parser.add_argument('--subsample', type=int, default=1,
                        help='Subsample factor (default: 1 = no subsampling)')
    
    args = parser.parse_args()
    
    # Validate input
    try:
        csv_files = validate_input(args.csv_dir)
        print(f"✓ Found {len(csv_files)} CFD data file(s)")
        
        if args.verbose:
            for csv_file in csv_files:
                print(f"  - {os.path.basename(csv_file)}")
    except ValueError as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
    
    print(f"\n{'='*70}")
    print("PhysicsMLP3D Training Configuration")
    print('='*70)
    print(f"Input Directory:      {args.csv_dir}")
    print(f"Model Name:           {args.model_name}")
    print(f"Architecture:         PhysicsMLP3D ({args.n_layers}x{args.hidden}, tanh, skip)")
    print(f"Inputs:               (x, y, z, ws) -> 4 features")
    print(f"Epochs:               {args.epochs}")
    print(f"Batch Size:           {args.batch_size}")
    print(f"Collocation Points:   {args.cpoints}")
    print(f"Learning Rate:        {args.learning_rate} (CosineDecay)")
    print(f"Physics Weight alpha: {args.alpha}")
    print(f"Early Stop Patience:  {args.patience}")
    print(f"Max Points/File:      {args.max_points_per_file}")
    print(f"Velocity Filter:      |U| > {args.umag_min} m/s")
    if args.init_weights:
        print(f"Fine-tuning from:     {args.init_weights}")
    if args.output_dir:
        print(f"Output Directory:     {args.output_dir}")
    print('='*70 + "\n")
    
    # Prepare sys.argv for MPWB2_CFD main()
    sys.argv = [
        'train_cfd.py',
        args.csv_dir,
        args.model_name,
        '--epochs', str(args.epochs),
        '--batch_size', str(args.batch_size),
        '--cpoints', str(args.cpoints),
        '--learning_rate', str(args.learning_rate),
        '--patience', str(args.patience),
        '--alpha', str(args.alpha),
        '--nu', str(args.nu),
        '--w_div', str(args.w_div),
        '--test_size', str(args.test_size),
        '--val_size', str(args.val_size),
        '--hidden', str(args.hidden),
        '--n_layers', str(args.n_layers),
        '--max_points_per_file', str(args.max_points_per_file),
        '--umag_min', str(args.umag_min),
    ]
    
    # Add init_weights if provided
    if args.init_weights:
        sys.argv.extend(['--init_weights', args.init_weights])
    
    # Add output_dir if provided
    if args.output_dir:
        sys.argv.extend(['--output_dir', args.output_dir])
    
    # Add subsample factor
    if args.subsample > 1:
        sys.argv.extend(['--subsample', str(args.subsample)])
    
    # Call MPWB2_CFD training
    _train_start = time.time()
    try:
        train_main()
        
        # Determine experiment directory
        if args.output_dir:
            experiment_dir = args.output_dir
        else:
            # Legacy: find most recent experiment_cfd_* directory
            experiment_dirs = glob.glob('experiment_cfd_*')
            experiment_dir = sorted(experiment_dirs)[-1] if experiment_dirs else None
        
        if experiment_dir and os.path.isdir(experiment_dir):
            print(f"\n{'='*70}")
            print("Training Complete!")
            print('='*70)
            summary = create_training_summary(experiment_dir, args.model_name)
            print(f"Model Directory: {summary['model_dir']}")
            print(f"Weights:         {os.path.basename(summary['weights'])}")
            print(f"Normalization:   {os.path.basename(summary['normalization'])}")
            print(f"Model Meta:      {os.path.basename(summary['model_meta'])}")
            print('='*70)
            
            # Print summary as environment variables for shell integration
            _elapsed = time.time() - _train_start
            _h, _m, _s = int(_elapsed//3600), int((_elapsed%3600)//60), int(_elapsed%60)
            print(f"[TIMER] total={_h}h {_m}m {_s}s  ({_elapsed/60:.1f} min)")
            print(f"\nTRAINING_COMPLETE=True")
            print(f"MODEL_DIR={summary['model_dir']}")
            print(f"MODEL_WEIGHTS={summary['weights']}")
            print(f"MODEL_NORMALIZATION={summary['normalization']}")
            print(f"MODEL_META={summary['model_meta']}")
    
    except Exception as e:
        print(f"\n✗ Training failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
