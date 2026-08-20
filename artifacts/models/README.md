# Model artifacts

These compact JSON logistic models were trained only on the repository's clearly labelled synthetic demonstration data. They are not validated for production or for decisions about real people.

The `.sha256` sibling of each JSON file is verified before loading. The files contain numeric coefficients and metadata only—no pickle or executable serialization. `evaluation.json` is the machine-readable record of split boundaries, validation comparison, held-out metrics, confusion matrices, threshold costs, and permutation importance.

Rebuild with `python scripts/train_models.py`; see `docs/MODEL_CARD.md` for intended and prohibited uses.
