# Plan: profile from endpoint telemetry (approach 2), for later

Status: **not started.** Approach (1), in-process measurement, is live
(`inproc.py` + `ProfilerInvestigator`/`EndpointInvestigator`).  This is
the follow-on that turns "profile" into "run once, read telemetry."

## Why

The surrogate selector needs a resource fingerprint of each candidate's
inference to predict its edge (Pi) runtime.  Approach (1) measures the
call in-process with `resource.getrusage` + `psutil.io_counters`.  That
works and is staging-free, but:

- it re-runs the inference *only to measure it* (a second execution on
  top of the one the twin already does for real), and
- in-process counters include a little of the task-runner's own
  activity and give peak RSS, not the isolated child's PSS.

The rhapsody endpoint **already records** per-task telemetry -- task
lifecycle plus `ResourceUpdate` (cpu %, memory %, disk read/write bytes)
polled while the task runs -- into
`telemetry-output/session.*.telemetry.jsonl` (the `[telemetry]` extra;
this is what `service/collect_reports.py` renders).  So the cost of a
candidate's inference is captured for free when it runs as a normal
task.  Approach (2): read that instead of re-running under a profiler.

## Shape

1. **Correlate a task to its telemetry.** The DT already ties a task uid
   to its twin/component (`DTRuntime.note_task`, carried in `twin_list`
   as `tasks`/`task_components`).  The telemetry events carry the same
   `task_id`.  A helper reads the session jsonl and, for a given uid,
   returns the `{total_seconds, cpu_seconds, disk_read_bytes,
   disk_write_bytes, memory_bytes}` aggregated from that task's
   `TaskStarted`/`TaskCompleted` span and its `ResourceUpdate` samples.

2. **Profiler investigator becomes a reader, not a runner.** When the
   agent asks to profile a candidate, the profiler no longer executes
   the inference: it (a) ensures the candidate has run at least once
   (the twin's normal inference already does this), (b) looks up that
   task's uid, (c) reads the telemetry record for it, (d) returns the
   same six-key profile dict.  No second execution, no subprocess.

3. **Keep the schema.** Emit the exact keys `inproc.py` and the
   subprocess profiler use, so `data.csv`, `endpoint_trainer.py`, and
   the Pi predictor are unchanged; approach (2) is a drop-in source
   swap.

## Open questions to resolve when building it

- **Telemetry access from the profiler.** The jsonl lives on the
  endpoint; the profiler component's `main_loop` runs on the broker.
  Reading it needs either (i) a small function-task on the endpoint that
  greps the jsonl for the uid and returns the record (endpoint-side,
  staging-free -- preferred), or (ii) an engine-side telemetry API on
  the DT service (see digital.twins#36, engine-side telemetry) that
  surfaces per-task metrics to the runtime.
- **Timing / flush.** `ResourceUpdate` is polled (default ~0.5 s); a
  very fast inference may produce few samples.  Fall back to the task
  span's wall/cpu when samples are sparse, or lower the poll interval
  for the profiling window.
- **Attribution granularity.** Confirm the telemetry `task_id` matches
  the uid the DT records for the *inference* task specifically (not a
  wrapping flow task), mirroring the exact-attribution work the
  dashboard relies on.
- **Isolation.** Telemetry measures the task as it actually ran
  (shared with whatever else the endpoint was doing).  For a
  comparative fingerprint that is acceptable; note it if absolute
  numbers ever matter.

## Relationship to the remaining executable-task hand-offs

The Pi-predictor's `train_model` / `call_inference` (`endpoint_trainer.py`
/ `endpoint_eval.py`) are still executable tasks whose *command-builder*
bodies prepare input files (`model.json`, `inf.json`).  `data.csv` is now
endpoint-local (the append moved to a function-task); `inf.json` in
`call_inference` is still written broker-side.  Those are the prediction
*model*, not profiling, and are out of scope here -- but the same fix
applies: write their inputs in a preceding function-task (endpoint-side)
or pass them as command arguments.  Track that alongside this.
