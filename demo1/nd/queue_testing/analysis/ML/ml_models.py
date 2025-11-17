import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import xgboost as xgb
import warnings
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.neural_network import MLPRegressor
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.callbacks import EarlyStopping
warnings.filterwarnings('ignore')

outliers=False
num_cores=64

ahead = pd.read_csv('ahead.csv')
times = pd.read_csv('times.csv')

del ahead['num_cores']

df = pd.merge(times, ahead, on='file')
df['queuing_delay'] = df['started'] - df['submitted']
df['submitted_dt'] = pd.to_datetime(df['submitted'], unit='s') - pd.Timedelta('04:00:00')
df['started_dt'] = pd.to_datetime(df['started'], unit='s') - pd.Timedelta('04:00:00')

# Sort by submission time
df = df.sort_values('submitted_dt')
df.to_csv('combined_data.csv', index=False)

df_no_outliers = df.copy()

if outliers == False:
    for num_cores in [4, 16, 64]:
        mask = df_no_outliers['num_cores'] == num_cores
        subset = df_no_outliers.loc[mask, 'queuing_delay']
        
        Q1 = subset.quantile(0.25)
        Q3 = subset.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        # Keep only rows within bounds for this num_cores group
        valid = (subset >= lower_bound) & (subset <= upper_bound)
        df_no_outliers = df_no_outliers[~mask | valid]

    df = df_no_outliers

df = df[df['num_cores'] == num_cores]

# Convert datetime columns if needed
df['submitted_dt'] = pd.to_datetime(df['submitted_dt'])
df['started_dt'] = pd.to_datetime(df['started_dt'])

# Extract time-based features
df['hour'] = df['submitted_dt'].dt.hour
df['day_of_week'] = df['submitted_dt'].dt.dayofweek
df['minute'] = df['submitted_dt'].dt.minute

# Calculate additional features
df['total_jobs'] = df['jobs_ahead'] + df['jobs_in_my_queue'] + df['jobs_running']
df['queue_load'] = df['jobs_ahead'] + df['jobs_in_my_queue']

feature_columns = [
    'num_cores',
    'jobs_ahead',
    'jobs_in_my_queue',
    'jobs_running',
    'hour',
    'day_of_week',
    'minute',
    'total_jobs',
    'queue_load'
]

X = df[feature_columns]
y = df['queuing_delay']

correlations = df[feature_columns + ['queuing_delay']].corr()['queuing_delay'].sort_values(ascending=False)
print(correlations)

# Split the data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print(f"\nTraining set size: {X_train.shape[0]}")
print(f"Test set size: {X_test.shape[0]}")

# Scale the features
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Prepare sequence data for LSTM/GRU/Transformer
def create_sequences(X, y, seq_length=10):
    """Create sequences for time-series models"""
    X_seq, y_seq = [], []
    for i in range(len(X) - seq_length):
        X_seq.append(X[i:i+seq_length])
        y_seq.append(y[i+seq_length])
    return np.array(X_seq), np.array(y_seq)

# Create sequences (using scaled data)
seq_length = 10
X_train_seq, y_train_seq = create_sequences(X_train_scaled, y_train.values, seq_length)
X_test_seq, y_test_seq = create_sequences(X_test_scaled, y_test.values, seq_length)

print(f"\nSequence training set size: {X_train_seq.shape[0]}")
print(f"Sequence test set size: {X_test_seq.shape[0]}")
print(f"Sequence shape: {X_train_seq.shape}")

# Initialize models
models = {
    'Linear Regression': LinearRegression(),
    'Ridge Regression': Ridge(alpha=1.0),
    'Lasso Regression': Lasso(alpha=1.0),
    'Random Forest': RandomForestRegressor(n_estimators=100, random_state=42, max_depth=10),
    'Gradient Boosting': GradientBoostingRegressor(n_estimators=100, random_state=42, max_depth=5),
    'XGBoost': xgb.XGBRegressor(n_estimators=100, random_state=42, max_depth=5, learning_rate=0.1),
    'Support Vector Regression': SVR(kernel='rbf', C=100, gamma='scale'),
    'Neural Network': MLPRegressor(hidden_layer_sizes=(100, 50), max_iter=500, random_state=42)
}

# Define deep learning models
def create_lstm_model(input_shape):
    model = keras.Sequential([
        layers.LSTM(64, return_sequences=True, input_shape=input_shape),
        layers.Dropout(0.2),
        layers.LSTM(32),
        layers.Dropout(0.2),
        layers.Dense(16, activation='relu'),
        layers.Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return model

def create_gru_model(input_shape):
    model = keras.Sequential([
        layers.GRU(64, return_sequences=True, input_shape=input_shape),
        layers.Dropout(0.2),
        layers.GRU(32),
        layers.Dropout(0.2),
        layers.Dense(16, activation='relu'),
        layers.Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return model

def create_transformer_model(input_shape):
    inputs = layers.Input(shape=input_shape)
    
    # Multi-head attention
    attention = layers.MultiHeadAttention(num_heads=4, key_dim=32)(inputs, inputs)
    attention = layers.Dropout(0.2)(attention)
    attention = layers.LayerNormalization(epsilon=1e-6)(attention + inputs)
    
    # Feed-forward network
    ffn = layers.Dense(64, activation='relu')(attention)
    ffn = layers.Dropout(0.2)(ffn)
    ffn = layers.Dense(input_shape[-1])(ffn)
    ffn = layers.LayerNormalization(epsilon=1e-6)(ffn + attention)
    
    # Global average pooling and output
    pooled = layers.GlobalAveragePooling1D()(ffn)
    outputs = layers.Dense(16, activation='relu')(pooled)
    outputs = layers.Dense(1)(outputs)
    
    model = keras.Model(inputs=inputs, outputs=outputs)
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return model

# Train and evaluate models
results = {}
predictions = {}

print("\n" + "="*50)
print("MODEL TRAINING AND EVALUATION")
print("="*50)

for name, model in models.items():
    print(f"\n{name}:")
    print("-" * 40)
    
    # Use scaled data for models that benefit from scaling
    if name in ['Ridge Regression', 'Lasso Regression', 'Support Vector Regression', 'Neural Network']:
        model.fit(X_train_scaled, y_train)
        y_pred = model.predict(X_test_scaled)
        
        # Cross-validation
        cv_scores = cross_val_score(model, X_train_scaled, y_train, 
                                     cv=5, scoring='neg_mean_squared_error')
    else:
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        
        # Cross-validation
        cv_scores = cross_val_score(model, X_train, y_train, 
                                     cv=5, scoring='neg_mean_squared_error')
    
    # Calculate metrics
    mse = mean_squared_error(y_test, y_pred)
    rmse = np.sqrt(mse)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    # Store results
    results[name] = {
        'MSE': mse,
        'RMSE': rmse,
        'MAE': mae,
        'R2': r2,
        'CV_RMSE': np.sqrt(-cv_scores.mean())
    }
    predictions[name] = y_pred
    
    print(f"Mean Squared Error (MSE): {mse:.2f}")
    print(f"Root Mean Squared Error (RMSE): {rmse:.2f}")
    print(f"Mean Absolute Error (MAE): {mae:.2f}")
    print(f"R² Score: {r2:.4f}")
    print(f"Cross-Validation RMSE: {np.sqrt(-cv_scores.mean()):.2f}")

# Train deep learning models
early_stop = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)

# LSTM
print(f"\nLSTM:")
print("-" * 40)
lstm_model = create_lstm_model((seq_length, X_train.shape[1]))
history_lstm = lstm_model.fit(
    X_train_seq, y_train_seq,
    epochs=100,
    batch_size=32,
    validation_split=0.2,
    callbacks=[early_stop],
    verbose=0
)
y_pred_lstm = lstm_model.predict(X_test_seq, verbose=0).flatten()

mse_lstm = mean_squared_error(y_test_seq, y_pred_lstm)
rmse_lstm = np.sqrt(mse_lstm)
mae_lstm = mean_absolute_error(y_test_seq, y_pred_lstm)
r2_lstm = r2_score(y_test_seq, y_pred_lstm)

results['LSTM'] = {
    'MSE': mse_lstm,
    'RMSE': rmse_lstm,
    'MAE': mae_lstm,
    'R2': r2_lstm,
    'CV_RMSE': rmse_lstm  # No cross-validation for simplicity
}
predictions['LSTM'] = y_pred_lstm

print(f"Mean Squared Error (MSE): {mse_lstm:.2f}")
print(f"Root Mean Squared Error (RMSE): {rmse_lstm:.2f}")
print(f"Mean Absolute Error (MAE): {mae_lstm:.2f}")
print(f"R² Score: {r2_lstm:.4f}")

# GRU
print(f"\nGRU:")
print("-" * 40)
gru_model = create_gru_model((seq_length, X_train.shape[1]))
history_gru = gru_model.fit(
    X_train_seq, y_train_seq,
    epochs=100,
    batch_size=32,
    validation_split=0.2,
    callbacks=[early_stop],
    verbose=0
)
y_pred_gru = gru_model.predict(X_test_seq, verbose=0).flatten()

mse_gru = mean_squared_error(y_test_seq, y_pred_gru)
rmse_gru = np.sqrt(mse_gru)
mae_gru = mean_absolute_error(y_test_seq, y_pred_gru)
r2_gru = r2_score(y_test_seq, y_pred_gru)

results['GRU'] = {
    'MSE': mse_gru,
    'RMSE': rmse_gru,
    'MAE': mae_gru,
    'R2': r2_gru,
    'CV_RMSE': rmse_gru
}
predictions['GRU'] = y_pred_gru

print(f"Mean Squared Error (MSE): {mse_gru:.2f}")
print(f"Root Mean Squared Error (RMSE): {rmse_gru:.2f}")
print(f"Mean Absolute Error (MAE): {mae_gru:.2f}")
print(f"R² Score: {r2_gru:.4f}")

# Transformer
print(f"\nTransformer:")
print("-" * 40)
transformer_model = create_transformer_model((seq_length, X_train.shape[1]))
history_transformer = transformer_model.fit(
    X_train_seq, y_train_seq,
    epochs=100,
    batch_size=32,
    validation_split=0.2,
    callbacks=[early_stop],
    verbose=0
)
y_pred_transformer = transformer_model.predict(X_test_seq, verbose=0).flatten()

mse_transformer = mean_squared_error(y_test_seq, y_pred_transformer)
rmse_transformer = np.sqrt(mse_transformer)
mae_transformer = mean_absolute_error(y_test_seq, y_pred_transformer)
r2_transformer = r2_score(y_test_seq, y_pred_transformer)

results['Transformer'] = {
    'MSE': mse_transformer,
    'RMSE': rmse_transformer,
    'MAE': mae_transformer,
    'R2': r2_transformer,
    'CV_RMSE': rmse_transformer
}
predictions['Transformer'] = y_pred_transformer

print(f"Mean Squared Error (MSE): {mse_transformer:.2f}")
print(f"Root Mean Squared Error (RMSE): {rmse_transformer:.2f}")
print(f"Mean Absolute Error (MAE): {mae_transformer:.2f}")
print(f"R² Score: {r2_transformer:.4f}")

# Create results summary DataFrame
results_df = pd.DataFrame(results).T
results_df = results_df.sort_values('RMSE')

print("\n" + "="*50)
print("RESULTS SUMMARY (sorted by RMSE)")
print("="*50)
print(results_df)

# Find the best model
best_model_name = results_df.index[0]
print(f"\n🏆 Best Model: {best_model_name}")
print(f"   RMSE: {results_df.loc[best_model_name, 'RMSE']:.2f} seconds")
print(f"   MAE: {results_df.loc[best_model_name, 'MAE']:.2f} seconds")
print(f"   R²: {results_df.loc[best_model_name, 'R2']:.4f}")

# Feature importance for tree-based models
print("\n" + "="*50)
print("FEATURE IMPORTANCE")
print("="*50)

for name in ['Random Forest', 'Gradient Boosting', 'XGBoost']:
    if name in models:
        model = models[name]
        model.fit(X_train, y_train)
        
        importance_df = pd.DataFrame({
            'feature': feature_columns,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        print(f"\n{name}:")
        print(importance_df)

# Visualization
fig, axes = plt.subplots(2, 2, figsize=(15, 12))

# 1. Model comparison
ax1 = axes[0, 0]
results_df['RMSE'].plot(kind='barh', ax=ax1, color='skyblue')
ax1.set_xlabel('RMSE (seconds)')
ax1.set_title('Model Comparison - RMSE')
ax1.grid(axis='x', alpha=0.3)

# 2. R² Score comparison
ax2 = axes[0, 1]
results_df['R2'].plot(kind='barh', ax=ax2, color='lightgreen')
ax2.set_xlabel('R² Score')
ax2.set_title('Model Comparison - R² Score')
ax2.grid(axis='x', alpha=0.3)

# 3. Actual vs Predicted for best model
ax3 = axes[1, 0]
best_predictions = predictions[best_model_name]
# Handle sequence models
if best_model_name in ['LSTM', 'GRU', 'Transformer']:
    y_test_plot = y_test_seq
else:
    y_test_plot = y_test

ax3.scatter(y_test_plot, best_predictions, alpha=0.5)
ax3.plot([y_test_plot.min(), y_test_plot.max()], [y_test_plot.min(), y_test_plot.max()], 
         'r--', lw=2, label='Perfect Prediction')
ax3.set_xlabel('Actual Queuing Delay (seconds)')
ax3.set_ylabel('Predicted Queuing Delay (seconds)')
ax3.set_title(f'Actual vs Predicted - {best_model_name}')
ax3.legend()
ax3.grid(alpha=0.3)

# 4. Residuals plot
ax4 = axes[1, 1]
residuals = y_test_plot - best_predictions
ax4.scatter(best_predictions, residuals, alpha=0.5)
ax4.axhline(y=0, color='r', linestyle='--', lw=2)
ax4.set_xlabel('Predicted Queuing Delay (seconds)')
ax4.set_ylabel('Residuals (seconds)')
ax4.set_title(f'Residual Plot - {best_model_name}')
ax4.grid(alpha=0.3)

plt.tight_layout()
if outliers:
    plt.savefig('outliers/model_comparison.pdf', dpi=300, bbox_inches='tight')
else:
    plt.savefig('no_outliers/model_comparison.pdf', dpi=300, bbox_inches='tight')

# Plot training history for deep learning models
fig, axes = plt.subplots(1, 3, figsize=(15, 4))

axes[0].plot(history_lstm.history['loss'], label='Train')
axes[0].plot(history_lstm.history['val_loss'], label='Validation')
axes[0].set_title('LSTM Training History')
axes[0].set_xlabel('Epoch')
axes[0].set_ylabel('Loss (MSE)')
axes[0].legend()
axes[0].grid(alpha=0.3)

axes[1].plot(history_gru.history['loss'], label='Train')
axes[1].plot(history_gru.history['val_loss'], label='Validation')
axes[1].set_title('GRU Training History')
axes[1].set_xlabel('Epoch')
axes[1].set_ylabel('Loss (MSE)')
axes[1].legend()
axes[1].grid(alpha=0.3)

axes[2].plot(history_transformer.history['loss'], label='Train')
axes[2].plot(history_transformer.history['val_loss'], label='Validation')
axes[2].set_title('Transformer Training History')
axes[2].set_xlabel('Epoch')
axes[2].set_ylabel('Loss (MSE)')
axes[2].legend()
axes[2].grid(alpha=0.3)

plt.tight_layout()
if outliers:
    plt.savefig('outliers/deep_learning_training_history.pdf', dpi=300, bbox_inches='tight')
else:
    plt.savefig('no_outliers/deep_learning_training_history.pdf', dpi=300, bbox_inches='tight')

# Save results to CSV
if outliers:
    results_df.to_csv('outliers/model_results.csv')
else:
    results_df.to_csv('no_outliers/model_results.csv')
print("\n" + "="*50)
print("ANALYSIS COMPLETE")
print("="*50)