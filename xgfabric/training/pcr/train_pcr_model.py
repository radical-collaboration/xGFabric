#!/usr/bin/env python3
"""
Train Principal Component Regression model and save coefficients.

Usage:
    python train_pcr_model.py <input_csv> <xyz_name>

Arguments:
    input_csv: Path to CSV file with columns 'out_values' and 'target_values'
    xyz_name: String identifier for the sensor location (used in output filename)

Output:
    Saves coefficients to 'pcr_coefficients_<xyz_name>.csv'
"""

import argparse
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler



def train_pcr_model(input_csv: str, xyz_name: str, n_components: int = 12, sequence_length: int = 12):
    """
    Train PCR model and save coefficients.
    
    Parameters:
    -----------
    input_csv : str
        Path to CSV with 'out_values' and 'target_values' columns
    xyz_name : str
        Identifier for output filename
    n_components : int
        Number of PCA components (default: 12)
    sequence_length : int
        Length of input sequences (default: 12)
    """
    # Load data
    df = pd.read_csv(input_csv)
    
    # Create sequences from out_values
    out_values = df['out_values'].values
    target_values = df['target_values'].values
    
    # Build sequences of length sequence_length
    X = []
    y = []
    for i in range(len(out_values) - sequence_length + 1):
        seq = out_values[i:i + sequence_length]
        target = target_values[i + sequence_length - 1]  # Target corresponds to last value in sequence
        X.append(seq)
        y.append(target)
    
    X = np.array(X)
    y = np.array(y)
    
    print(f"Training data: {X.shape[0]} sequences of length {sequence_length}")
    
    # Step 1: Standardize
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Step 2: PCA
    n_comp = min(n_components, sequence_length)
    pca = PCA(n_components=n_comp)
    X_pca = pca.fit_transform(X_scaled)
    
    # Step 3: Linear Regression
    regressor = LinearRegression()
    regressor.fit(X_pca, y)
    
    print(f"PCA explained variance: {sum(pca.explained_variance_ratio_):.4f}")
    print(f"Regression coefficients shape: {regressor.coef_.shape}")
    
    # Save all coefficients in a single CSV
    # Row format: scaler_mean, scaler_scale, pca_components (flattened), pca_mean, reg_coef, reg_intercept
    
    coefficients = {
        'scaler_mean': scaler.mean_.tolist(),
        'scaler_scale': scaler.scale_.tolist(),
        'pca_components': pca.components_.flatten().tolist(),
        'pca_mean': pca.mean_.tolist(),
        'pca_n_components': n_comp,
        'sequence_length': sequence_length,
        'reg_coef': regressor.coef_.tolist(),
        'reg_intercept': regressor.intercept_
    }
    
    # Save as simple CSV with one row per coefficient type
    output_file = f'pcr_coefficients_{xyz_name}.csv'
    
    # Create a flat representation
    flat_data = []
    flat_data.append(['scaler_mean'] + list(scaler.mean_))
    flat_data.append(['scaler_scale'] + list(scaler.scale_))
    flat_data.append(['pca_mean'] + list(pca.mean_))
    for i, comp in enumerate(pca.components_):
        flat_data.append([f'pca_component_{i}'] + list(comp))
    flat_data.append(['reg_coef'] + list(regressor.coef_))
    flat_data.append(['reg_intercept', regressor.intercept_])
    flat_data.append(['n_components', n_comp])
    flat_data.append(['sequence_length', sequence_length])
    
    # Find max length for padding
    max_len = max(len(row) for row in flat_data)
    
    # Pad rows to same length
    for row in flat_data:
        while len(row) < max_len:
            row.append('')
    
    # Save to CSV
    out_df = pd.DataFrame(flat_data)
    out_df.to_csv(output_file, index=False, header=False)
    
    print(f"Coefficients saved to: {output_file}")
    
    return coefficients


def main():
    parser = argparse.ArgumentParser(description='Train PCR model and save coefficients')
    parser.add_argument('input_csv', help='Path to CSV with out_values and target_values columns')
    parser.add_argument('xyz_name', help='Identifier string for output filename (e.g., "50_46_1")')
    parser.add_argument('--n_components', type=int, default=12, help='Number of PCA components (default: 12)')
    parser.add_argument('--sequence_length', type=int, default=12, help='Sequence length (default: 12)')
    
    args = parser.parse_args()
    
    train_pcr_model(args.input_csv, args.xyz_name, args.n_components, args.sequence_length)


if __name__ == '__main__':
    main()
