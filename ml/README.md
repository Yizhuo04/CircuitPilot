# ML experiment workflow

No CircuitPilot-trained detector or real-photo accuracy result is bundled. The
running application uses manual homography by default. Its expected-layout overlay
is not a component detector. Unit tests use synthetic fixtures and model doubles;
their numeric results are not evidence of real-world model performance.

## Collect and label

1. Select a supported physical board only after continuity and geometry measurements.
2. Photograph distinct physical setups across lighting, angles, cameras, and partial
   assemblies. Seek explicit consent; training opt-in is off by default in the app.
3. Use **Data & pilot** to draw class boxes and record physical setup/capture session
   IDs. Mark labels reviewed only after checking them. Class order is resistor, LED,
   push_button, wire_endpoint, board_outline.
4. Export the consented manifest. Download photos using your own authenticated
   account; the CLI prompts for a password without persisting it:

```sh
uv run --locked python -m app.dataset_cli download path/to/exported-manifest.json \
  ml/datasets/initial --email your-account-email --api-url http://127.0.0.1:8000
uv run --locked python -m app.dataset_cli export-yolo \
  ml/datasets/initial/manifest.json ml/datasets/yolo-v1 --seed 42
```

The exporter groups transitively by physical setup, capture session, and identical
content hash. Those groups cannot cross train/validation/test. It targets 70/15/15
by group count, reserving at least one validation and test group. Fewer than three
independent groups is rejected. Small splits may differ substantially from target
ratios; group integrity takes precedence. Exact hashes do not detect all visual
near-duplicates: review adjacent sessions and burst captures manually.

Every export verifies consent, reviewed status, bounding boxes, file hashes, PNG
format, dimensions, and paths. The output records seed, split membership, and source
provenance. Empty images are valid negative examples. Real data remains outside Git.

## Optional detector training

Use an isolated environment and deliberately select a tested YOLO/PyTorch version
compatible with your hardware. The optional Ultralytics dependency is not installed
in the deterministic MVP or locked as a production dependency, because no real
training dataset or hardware target is available yet. Record exact versions with
your experiment and freeze them before comparing runs.

Review [Ultralytics licensing](https://www.ultralytics.com/license) before choosing
weights or distributing a model; commercial use is not automatically unrestricted.
The training wrapper requires trusted local starting weights and never downloads
an unknown model implicitly. After installing your reviewed training dependency
alongside the CircuitPilot package:

```sh
python ml/training/train.py ml/datasets/yolo-v1 \
  --weights /absolute/path/to/trusted-starting-weights.pt \
  --epochs 50 --seed 42 --output ml/runs/experiment-001
```

Training and selection use train/validation. The wrapper then evaluates the frozen
best model on test and records metrics, model hash, dataset provenance hash, epochs,
and seed. Do not tune against the final test set. Re-running on a seen test set is
not a fresh independent evaluation. A target of 300–500 labeled photos is a starting
collection goal, not an accuracy guarantee.

## Evaluate and integrate

`ml/evaluation/evaluate.py` accepts lists of `{image_id, class_name, box}` ground
truth and `{image_id, class_name, box, score}` predictions. Boxes are pixel-space
`[x,y,width,height]`. It calculates AP@0.5, precision/recall at score 0.5, per-class
counts, and ten-bin detection ECE. Empty ground-truth classes have undefined AP,
not perfect AP. Matching is class/image-specific and one-to-one; duplicate detections
count against precision.

```sh
uv run --locked python ml/evaluation/evaluate.py held-out-truth.json predictions.json \
  --output ml/runs/held-out-evaluation.json
```

Calibrate scores using a separate validation/calibration set before interpreting
them probabilistically. Report endpoint localization error separately; bounding-box
centers are insufficient for confident pin-hole assignment. Occlusion and class-wise
false negatives must remain visible.

After real evaluation, point `CIRCUITPILOT_DETECTOR_MODEL_DIR` at an experiment folder
containing `training-report.json` and `train/weights/best.pt`, and install the chosen
optional runtime in both backend and worker environments. Startup checks the model
hash and class names. No arbitrary user upload can configure weights. The adapter
reports possible observations and not-observed/occluded states; it never edits the
plan or claims electrical verification. Its real-model execution remains untested
until trusted evaluated weights are supplied.
