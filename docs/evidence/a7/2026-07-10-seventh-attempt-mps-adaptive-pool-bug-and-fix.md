# PyTorch MPS limitation: AdaptiveAvgPool2d requires divisible input/output sizes

## What happened

Operator ran the real retrain command on their Mac (M4 Max, real MPS
device, not this session's sandbox):

```bash
caffeinate -i uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v3/index.csv \
    --epochs 20 --num-workers 8 \
    --out models/tier2_cnn_v3.pt \
    --grouped-split-report Logs/reports/tier2_cnn_v3_grouped_split_report.json \
    --production-candidate
```

Console showed `Device: mps` (the v0.90.78 device-selection fix worked
correctly — MPS was genuinely selected), then crashed on the very first
training batch of epoch 1:

```
RuntimeError: Adaptive pool MPS: input sizes must be divisible by output
sizes. Non-divisible input sizes are not implemented on MPS device yet.
For now, you can manually transfer tensor to cpu in this case. Please
refer to this issue: https://github.com/pytorch/pytorch/issues/96056
```

No model checkpoint was ever written (crash occurred before the first
`torch.save`). The `evaluate_calibration.py` command that followed
correctly printed `[CNN] Skipped — cutouts CSV or model not found.` and
only reported Tier 1 XGBoost's (already-established, unrelated)
calibration KPIs — **not** new evidence for the Tier 2 CNN.
`calibration_report_missing` remained open after this run.

## Root cause (exact, not guessed)

`src/classify.py`'s `ConvBranch` (the three-branch CNN's shared
convolutional stack, used by `_build_cnn_model()` for every Tier 2 CNN
version including the frozen `benchmark_cnn_v1`) processes a 63×63 input:

```
63×63 -> Conv2d(1,32,3,pad=1) -> ReLU -> MaxPool2d(2)  -> 31×31
31×31 -> Conv2d(32,64,3,pad=1) -> ReLU -> MaxPool2d(2) -> 15×15
15×15 -> Conv2d(64,128,3,pad=1) -> ReLU -> AdaptiveAvgPool2d(4) -> 4×4
```

`15 / 4 = 3.75` — not evenly divisible. This is a real, documented
limitation of PyTorch's MPS backend (not this project's code, and not
fixable by changing training parameters): `adaptive_avg_pool2d` on MPS is
only implemented for input sizes evenly divisible by the output size.
Referenced upstream: <https://github.com/pytorch/pytorch/issues/96056>.
CPU and CUDA backends do not have this restriction — the model architecture
itself is not wrong, only the MPS kernel is incomplete relative to CPU/CUDA.

## Fix (commit pending on `main`)

Per the error message's own suggested workaround, `ConvBranch.forward()`
now iterates its `nn.Sequential`'s child layers manually instead of
calling `self.net(x)` directly, and moves the tensor to CPU **only** for
the `AdaptiveAvgPool2d` step when running on MPS, then back to the
original device immediately after:

```python
def forward(self, x):
    for layer in self.net:
        if isinstance(layer, nn.AdaptiveAvgPool2d) and x.device.type == "mps":
            x = layer(x.to("cpu")).to(x.device)
        else:
            x = layer(x)
    return x
```

Every other layer (both `Conv2d`s, both `ReLU`s, both `MaxPool2d`s, and
`Flatten`) runs on the original device (MPS) exactly as before; only the
one incompatible op is routed through CPU, and only when necessary.

**First implementation attempt was wrong and reverted**: an initial fix
split `self.net` into separate `self.conv`/`self.pool` attributes, which
changed `state_dict()` key names (`branch_sci.net.0.weight` ->
`branch_sci.conv.0.weight`) and **broke loading the frozen
`benchmark_cnn_v1` checkpoint** (`Skills/validate_model_weights.py` went
from `ALL PASSED` to `FAIL tier2_cnn.pt: _load_cnn_model() returned None`).
Caught by running that validator immediately after the change, before
committing. The corrected fix above keeps `self.net` as a single
`nn.Sequential` with unchanged layer order/indices, so `state_dict()` keys
are byte-identical to before — `Skills/validate_model_weights.py` now
reports `ALL PASSED` again, including `tier2_cnn.pt loaded and produced
valid 5-class output`.

Two new regression tests in `tests/test_classify.py`:
- `test_conv_branch_state_dict_keys_unchanged_by_mps_workaround` — asserts
  the exact key names that broke on the first attempt.
- `test_conv_branch_forward_matches_direct_sequential_call_on_cpu` —
  asserts the workaround is a byte-identical no-op on CPU (can't test MPS
  itself outside real Apple Silicon hardware, but this guards that the
  refactor didn't change CPU-path numerics).

Full suite 1845 passed / 2 deselected, ruff/mypy clean,
`Skills/validate_model_weights.py` → `ALL PASSED`.

## Predicted operator console after this fix

`Device: mps`, then per-epoch lines like
`Epoch 1/20  train_loss=...  val_loss=...  val_acc=...` completing all 20
epochs without a `RuntimeError`, ending in `Best val loss: ...` and
`Saved best weights -> models/tier2_cnn_v3.pt`. The subsequent
`evaluate_calibration.py` call should then show a real `[CNN]` section
(not `Skipped`) with Brier/ECE/Log-loss/ROC AUC/CV/bootstrap KPIs for the
actual retrained Tier 2 CNN.

**If it still shows `Adaptive pool MPS` or any other MPS RuntimeError**,
the root cause above was incomplete — re-diagnose from that new traceback
rather than patching this same area again.

## Status

`calibration_report_missing`: still open, pending the operator re-running
the retrain command with this fix merged. This is a real, upstream PyTorch
MPS gap worth being aware of for any future MPS training work in this
project: any `AdaptiveAvgPool2d` (or similar adaptive pooling op) with a
non-divisible input/output size will hit the same error on Apple Silicon
MPS, and needs the same CPU-detour workaround.
