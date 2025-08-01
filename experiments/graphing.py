import matplotlib.pyplot as plt
import pandas as pd

df_total = pd.read_csv("data/data.csv")

df = df_total.copy()
core_columns = [col for col in df.columns if col != 'experiment']
core_counts = [int(col.replace('*', '')) for col in core_columns]

mean_times = []
std_times = []
for col in core_columns:
    mean_time = df[col].mean()
    std_time = df[col].std()
    mean_times.append(mean_time)
    std_times.append(std_time)
    print(f"Cores {col.replace('*', '')}: Mean = {mean_time:.2f}s, Std = {std_time:.2f}s")

# Create the aggregated plot
plt.figure(figsize=(12, 8))

# Plot the mean line with error bars (2 standard deviations)
plt.errorbar(core_counts, mean_times, yerr=[2*s for s in std_times],
            color='darkblue',
            marker='o',
            linewidth=3,
            markersize=10,
            capsize=8,
            capthick=2,
            elinewidth=2,
            label='Mean ± 2 Std Dev')

plt.fill_between(core_counts,
                [m - 2*s for m, s in zip(mean_times, std_times)],
                [m + 2*s for m, s in zip(mean_times, std_times)],
                alpha=0.2,
                color='lightblue',
                label='±2 Std Dev')


for i, (cores, mean_time, std_time) in enumerate(zip(core_counts, mean_times, std_times)):
    if i == len(core_counts) - 1:
        plt.annotate(f'{mean_time:.1f}±{2*std_time:.1f}s',
                    xy=(cores, mean_time),
                    xytext=(-30, 40),
                    textcoords='offset points',
                    ha='center',
                    va='bottom',
                    fontsize=15,
                    fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3',
                             facecolor='yellow',
                             edgecolor='orange',
                             alpha=0.8),
                    arrowprops=dict(arrowstyle='->', 
                                   connectionstyle='arc3,rad=0',
                                   color='orange',
                                   lw=1.5))
                
    elif i == len(core_counts) - 3:
        plt.annotate(f'{mean_time:.1f}±{2*std_time:.1f}s',
                xy=(cores, mean_time),
                xytext=(120, 80),
                textcoords='offset points',
                ha='center',
                va='bottom',
                fontsize=15,
                fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3',
                            facecolor='yellow',
                            edgecolor='orange',
                            alpha=0.8),
                arrowprops=dict(arrowstyle='->', 
                                connectionstyle='arc3,rad=0',
                                color='orange',
                                lw=1.5))
    else:
        plt.annotate(f'{mean_time:.1f}±{2*std_time:.1f}s',
                    xy=(cores, mean_time),
                    xytext=(75, 40),
                    textcoords='offset points',
                    ha='center',
                    va='bottom',
                    fontsize=15,
                    fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3',
                            facecolor='yellow',
                            edgecolor='orange',
                            alpha=0.8),
                    arrowprops=dict(arrowstyle='->', 
                                connectionstyle='arc3,rad=0',
                                color='orange',
                                lw=1.5))


# Customize the plot
plt.xlabel('Number of Cores', fontsize=25, fontweight='bold')
plt.ylabel('Total Time (s)', fontsize=25, fontweight='bold')
plt.title('Mean Total Time vs Number of Cores',
         fontsize=30, fontweight='bold')

# Customize grid
plt.grid(True, alpha=0.3, linestyle='--')

# Set x-axis ticks to show actual core counts
plt.xticks(core_counts, [str(c) for c in core_counts], fontsize=15)
plt.yticks(fontsize=15)

plt.ylim(0, 4200)

# Add legend
plt.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=15)

# Add annotations for some key points
min_time_idx = mean_times.index(min(mean_times))

# Improve layout
plt.tight_layout()

plt.savefig('figures/speedup.pdf', dpi=300, bbox_inches='tight')

# Show the plot
plt.show()


