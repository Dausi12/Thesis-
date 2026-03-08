# Thesis-Ready Plot Style Guide

**Applies to:** All notebooks and reports in this repository  
**Purpose:** Ensure every figure produced is publication-grade, LaTeX-compatible, and consistent across scenarios A, B, and C.

---

## 1. LaTeX Document Preamble

Every `.tex` chapter or thesis main file that includes these figures must load:

```latex
\usepackage{amsmath,amssymb}
\usepackage{siunitx}          % proper unit typesetting in labels
\usepackage{libertine}        % match to the body font you use; alternatives below
```

**Font alternatives:**

| Thesis font      | LaTeX package         | `font.serif` rcParam value          |
|------------------|-----------------------|--------------------------------------|
| Libertine        | `\usepackage{libertine}`        | `"Libertinus Serif"`       |
| Latin Modern     | `\usepackage{lmodern}`          | `"Latin Modern Roman"`     |
| Times / STIX     | `\usepackage{times}`            | `"Times New Roman"`        |
| Computer Modern  | *(default, no package needed)*  | `"DejaVu Serif"`           |

---

## 2. Notebook Setup Block

Paste the block below **at the very top of every notebook**, before any plotting code.  
This is the single source of truth for visual style across all reports.

```python
# === Thesis-ready matplotlib + seaborn setup ===

import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib as mpl

# --- 1. Core rcParams (LaTeX rendering + typography) ---
plt.rcParams.update({
    "text.usetex":          True,                 # full LaTeX rendering
    "font.family":          "serif",
    "font.serif":           ["Libertinus Serif", "Latin Modern Roman",
                             "Times New Roman", "DejaVu Serif", "serif"],
    "font.size":            11,                   # match thesis body size
    "axes.labelsize":       11,
    "xtick.labelsize":      10,
    "ytick.labelsize":      10,
    "legend.fontsize":      10,
    "figure.dpi":           300,
    "savefig.dpi":          600,
    "figure.figsize":       (5.5, 3.8),           # single-column default
    "lines.linewidth":      1.4,
    "axes.linewidth":       0.8,
    "xtick.major.width":    0.8,
    "ytick.major.width":    0.8,
    "xtick.minor.visible":  True,
    "ytick.minor.visible":  True,
    "grid.alpha":           0.35,
    "grid.linestyle":       "--",
})

# --- 2. LaTeX preamble (must match thesis preamble) ---
plt.rcParams["text.latex.preamble"] = r"""
\usepackage{amsmath}
\usepackage{siunitx}
\usepackage{libertine}
\sisetup{detect-all}
"""

# --- 3. Seaborn style ---
sns.set_style("whitegrid", {
    "axes.facecolor":   "white",
    "figure.facecolor": "white",
    "grid.color":       "#dddddd",
    "axes.edgecolor":   "#333333",
    "xtick.color":      "#333333",
    "ytick.color":      "#333333",
})

# --- 4. Colorblind-safe palette ---
sns.set_palette("colorblind")   # alternatives: "deep", "muted", "Set2"
```

---

## 3. Figure Size Conventions

| Use case                     | `figsize` (inches)  |
|------------------------------|---------------------|
| Single-column figure         | `(5.0–5.5, 3.5–4.0)` |
| Two-column spanning figure   | `(7.0–7.5, 4.5–5.0)` |
| Tall panel (2×3 subplots)    | `(10, 7)`           |
| Wide panel (1×3 subplots)    | `(12, 4)`           |

---

## 4. Common Plot Templates

### 4.1 Boxplot + Swarmplot (group comparison)

```python
fig, ax = plt.subplots(figsize=(6, 4))
sns.boxplot(x="group", y="value", data=df, ax=ax, width=0.5)
sns.swarmplot(x="group", y="value", data=df, color="k", size=4, ax=ax)
ax.set_xlabel(r"Group")
ax.set_ylabel(r"Response (\si{\percent})")
ax.set_title(r"Comparison across conditions")
fig.tight_layout()
fig.savefig("figures/boxplot_groups.pdf", bbox_inches="tight", pad_inches=0.05)
```

### 4.2 Line Plot with Confidence Intervals (forecast / time series)

```python
fig, ax = plt.subplots(figsize=(6.5, 4))
sns.lineplot(x="time", y="power", hue="scenario",
             data=df_long, ax=ax, linewidth=1.8, errorbar="ci")
ax.set_xlabel(r"Time (\si{\hour})")
ax.set_ylabel(r"Power (\si{\kilo\watt})")
ax.legend(title="Scenario")
fig.tight_layout()
fig.savefig("figures/power_scenarios.pdf", bbox_inches="tight")
```

### 4.3 Violin Plot (distribution comparison)

```python
fig, ax = plt.subplots(figsize=(5.5, 4))
sns.violinplot(x="group", y="cost", data=df, inner="quartile", ax=ax)
sns.stripplot(x="group", y="cost", data=df, color="k", size=3, jitter=True, ax=ax)
ax.set_xlabel(r"Supplier Configuration")
ax.set_ylabel(r"Cost (\si{\euro\per\MWh})")
fig.tight_layout()
fig.savefig("figures/violin_costs.pdf", bbox_inches="tight")
```

---

## 5. Saving Figures

Always save as **vector PDF**. Never use `.png` for thesis figures.

```python
fig.savefig("figures/<descriptive_name>.pdf", bbox_inches="tight", pad_inches=0.05)
```

- `bbox_inches="tight"` — removes excess whitespace automatically  
- `pad_inches=0.05` — preserves a minimal uniform margin  
- Output directory should be `figures/` relative to each scenario folder

---

## 6. LaTeX Inclusion

```latex
\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.95\columnwidth]{figures/<descriptive_name>.pdf}
    \caption{<Caption describing what the figure shows and its significance.>}
    \label{fig:<descriptive_name>}
\end{figure}
```

For two-column spanning figures replace `0.95\columnwidth` with `\textwidth`.

---

## 7. Unit Label Reference (siunitx)

| Quantity                | LaTeX label                         |
|-------------------------|-------------------------------------|
| Power (kW)              | `\si{\kilo\watt}`                   |
| Energy (kWh)            | `\si{\kilo\watt\hour}`              |
| Price (€/MWh)           | `\si{\euro\per\mega\watt\hour}`     |
| Cost (€)                | `\si{\euro}`                        |
| Percentage (%)          | `\si{\percent}`                     |
| Time (h)                | `\si{\hour}`                        |
| Time (min)              | `\si{\minute}`                      |

---

## 8. Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `FileNotFoundError: latex` | LaTeX not installed on system | `sudo apt install texlive-full` or set `text.usetex: False` for drafts |
| Fonts not found | System lacks Libertine fonts | Install `fonts-linuxlibertine` or switch to `lmodern` |
| Overleaf compilation error | Missing `\usepackage{libertine}` in `.tex` preamble | Add the package to your Overleaf preamble |
| Blurry output in browser | `figure.dpi` too low | Already set to 300; use PDF for final output |
| `text.usetex` slow | Full LaTeX invoked per figure | Expected — acceptable for final thesis version; set `False` during development |

---

## 9. Quick-Draft Mode

During development, disable LaTeX rendering to speed up iteration:

```python
plt.rcParams["text.usetex"] = False
plt.rcParams["font.family"] = "sans-serif"
```

Switch back to `True` before generating final thesis figures.

---

## 10. Applicability

This style applies to all notebooks in the following directories:

- `A_Scenario_single_supplier_mandate/`
- `A_Scenario_single_supplier_mandate_mixed/`
- `B_Scenarion_Forecasting/`
- `B_Scenarion_Forecasting_mixed/`
- `C_Scenario_Battery_Optimization/`
- `scenarios_simulation/data/` (analysis and seed validation notebooks)

Any new notebook added to this repository must include the setup block from **Section 2** before producing plots.
