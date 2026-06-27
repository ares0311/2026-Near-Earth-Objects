# LOCAL SYSTEM PROFILE

## Purpose

This file records the local development machine profile so pipeline code, tests, and notebooks can be sized sensibly for this project.

Use this as an optimization guide, not as a portability requirement. The codebase should still run on smaller systems unless a task explicitly documents a higher local resource target.

Sensitive machine identifiers such as serial number, hardware UUID, provisioning UDID, and user account name are intentionally not recorded.

---

## Profile Snapshot

**Last verified:** 2026-05-01
**Sources:** macOS About This Mac screenshot, `system_profiler SPHardwareDataType SPSoftwareDataType`, `system_profiler SPDisplaysDataType`

| Category | Local value |
|---|---|
| Machine | MacBook Pro, 16-inch, Nov 2024 |
| Model identifier | Mac16,5 |
| Chip | Apple M4 Max |
| CPU cores | 16 total: 12 performance cores, 4 efficiency cores |
| GPU cores | 40-core integrated Apple GPU |
| Memory | 64 GB unified memory |
| Metal | Supported |
| Startup disk | Phi |
| macOS | macOS 26.4.1 |
| Darwin kernel | Darwin 25.4.0 |

---

## Local Optimization Defaults

Prefer these defaults when running project code on this machine:

- Keep default CPU-bound worker counts below full saturation. Start with `12` workers for local batch jobs and increase only after measuring.
- Keep at least `2` CPU cores free during interactive work.
- For I/O-heavy work, external-service queries, or live catalog access, use lower concurrency first, usually `4` to `6` workers, because remote service limits and disk throughput can dominate.
- Target peak memory below `48 GB` for routine local runs, leaving about `16 GB` for macOS, browser windows, notebooks, and the editor.
- Chunk large target or sector sweeps by target, sector, or candidate batch rather than loading all mission data into memory at once.
- Prefer memory-mapped arrays, columnar files, or streaming reads for large intermediate products.
- Cache downloaded raw data and expensive intermediate products locally, but do not commit large mission data or generated cache directories.
- For AI training and other accelerator-friendly numerical workloads, prefer
  the 40-core Apple GPU through Metal/MPS when the framework supports it and the
  result is reproducible. Report device selection in training logs and make any
  CPU fallback explicit.
- For CPU-heavy local batch jobs, prefer bounded multithreading or
  multiprocessing with configurable worker counts. Start from the worker and
  native-thread limits below rather than serial implementations, unless the task
  is too small or determinism requires serial execution.

---

## Numerical Threading Guidance

Avoid accidental oversubscription when combining process-level parallelism with NumPy, SciPy, Astropy, Lightkurve, or other native numerical libraries.

For multi-process workloads, set native numerical libraries to one thread per process unless profiling shows a better setting:

```bash
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_MAX_THREADS=1
```

For a single large numerical job, allow native libraries to use more threads, commonly `8` to `12`, then benchmark before raising the limit.

For PyTorch training on this Mac, prefer `mps`/Metal when
`torch.backends.mps.is_available()` is true. Training scripts should record the
selected device, batch size, worker count, and relevant thread settings in their
stdout logs and any training report artifact.

**All tensor data must be moved to the device explicitly.** Moving the model
alone (`.to(device)`) is not sufficient — input tensors, label tensors, and any
intermediate tensors passed to the model must also be moved. The canonical
pattern:
```python
device = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
model = model.to(device)
# Inside training loop:
inputs = inputs.to(device)
labels = labels.to(device)
```
Failing to move data tensors to the same device as the model will raise a
`RuntimeError` on MPS. This is a mandatory implementation requirement for all
training scripts in this project (Tier 2 CNN, Tier 3 Transformer, ensemble
stacker).

---

## Project-Specific Guidance

### Fetch

- Treat live ZTF, ALeRCE, ATLAS, MPC, JPL Horizons, CNEOS, Gaia, and similar calls as rate-limited external services.
- Default tests should mock these services.
- Live integration runs should be marked, opt-in, and operator-controlled unless the live-review policy has been approved.
- Prefer bounded query batches with progress and checkpoint/resume over monolithic sky-window downloads.

### Preprocess and Detect

- Process observations by survey window, target field, or candidate batch rather than loading all raw alerts into memory at once.
- Preserve raw observation provenance before applying quality filters or candidate caps.
- Write intermediate products incrementally so long runs can resume from the last completed stage.

### Link and Orbit

- Candidate linking can use local parallelism, but worker counts and candidate caps should be explicit in configuration.
- For large real-sky fields, prefer staged bounded runs with progress/ETA and persisted checkpoints before attempting uncapped linking.
- Keep orbit fitting deterministic and avoid native-thread oversubscription when running many candidate fits in parallel.

### Train, Score, and Classify

- Scoring and pathway classification should stay lightweight, deterministic, and pure where possible.
- These modules should run comfortably in unit tests without using the machine's full parallel capacity.
- Training jobs may use more CPU/GPU headroom, but batch size, worker count, and numerical threading must be explicit and reproducible.

### Audit and Reports

- Real-run audits should write compact JSON/CSV packets and avoid embedding large raw data products in reports.
- Notebooks may use this system's memory and CPU headroom for exploration, but production code should keep resource limits explicit.
- Reports should record enough provenance to reproduce results on this or another machine.

---

## Portability Rule

Optimizing for this MacBook Pro means choosing good defaults for local development. It does not mean hardcoding Apple-specific assumptions into scientific logic.

When performance-sensitive code needs system-specific behavior, expose it through configuration or documented runtime defaults.
