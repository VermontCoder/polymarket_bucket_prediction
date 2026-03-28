import matplotlib.pyplot as plt


def plot_bucket_predict_rates(bucket_rates: dict, title: str = "Bucket Predict True % — drag to rotate") -> None:
    xs, ys, zs = [], [], []
    for (x, y), rate in bucket_rates.items():
        xs.append(x)
        ys.append(y)
        zs.append(rate * 100)

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")

    scatter = ax.scatter(xs, ys, zs, c=zs, cmap="RdYlGn", s=10, alpha=0.7)

    ax.set_xlabel("X  (time_to_close // 2000)")
    ax.set_ylabel("Y  (diff_pct * 300 + 150)")
    ax.set_zlabel("Predict True %")
    ax.set_title(title)

    fig.colorbar(scatter, ax=ax, shrink=0.5, label="Predict True %")

    plt.tight_layout()
    plt.show()
