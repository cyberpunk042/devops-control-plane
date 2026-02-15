# Part 4: Job & CronJob — Generation Spec (Deltas from Deployment)

> Everything that differs from the Deployment flow.
> Job and CronJob share a common Job configuration section;
> CronJob adds scheduling fields on top.

---

## Collector Output Shape

### Job-specific fields (shared with CronJob)

```js
{
  name: "db-migrate",
  kind: "Job",                           // or "CronJob"
  image: "api:latest",

  // ── Job configuration ──
  command: "/bin/sh -c \"python manage.py migrate\"",
                                          // → container command: ["sh", "-c", "..."]
  args: "",                              // optional, space-separated → container args[]
  restartPolicy: "Never",               // "Never" | "OnFailure" → pod.spec.restartPolicy
  backoffLimit: 3,                       // int → spec.backoffLimit
  completions: 1,                        // int → spec.completions
  parallelism: 1,                        // int → spec.parallelism
  activeDeadlineSeconds: 600,            // int or null → spec.activeDeadlineSeconds
  ttlSecondsAfterFinished: 3600,         // int → spec.ttlSecondsAfterFinished

  // ── Shared fields ──
  envVars: [...],                         // same env var handling
  resources: {...},                       // resource limits
  companions: [...],                      // companion containers

  // ── Hidden for Jobs ──
  // port: — hidden
  // replicas: — hidden
  // serviceType: — hidden
  // readinessProbe: — hidden
  // livenessProbe: — hidden
  // volumes: — hidden
  // dependencies: — hidden
  // initContainers: — hidden
}
```

### CronJob-only fields (on top of Job)

```js
{
  // ...all Job fields above...
  kind: "CronJob",

  // ── CronJob scheduling ──
  schedule: "*/5 * * * *",               // cron expression → spec.schedule
  concurrencyPolicy: "Forbid",           // "Allow" | "Forbid" | "Replace"
                                          // → spec.concurrencyPolicy
  suspend: false,                        // checkbox → spec.suspend
  successfulJobsHistoryLimit: 3,         // int → spec.successfulJobsHistoryLimit
  failedJobsHistoryLimit: 1,             // int → spec.failedJobsHistoryLimit
  startingDeadlineSeconds: 300,          // int or null → spec.startingDeadlineSeconds
}
```

---

## Generated Manifests

### Job: `{output_dir}/{name}-job.yaml`

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migrate
  namespace: production
  labels:
    app: db-migrate
spec:
  backoffLimit: 3                            # ← svc.backoffLimit
  completions: 1                             # ← svc.completions
  parallelism: 1                             # ← svc.parallelism
  activeDeadlineSeconds: 600                 # ← svc.activeDeadlineSeconds (omit if null)
  ttlSecondsAfterFinished: 3600              # ← svc.ttlSecondsAfterFinished
  template:
    spec:
      restartPolicy: Never                   # ← svc.restartPolicy (REQUIRED for Jobs)
      containers:
        - name: db-migrate
          image: api:latest
          command:                            # ← svc.command
            - sh
            - -c
            - "python manage.py migrate"
          # args: [...]                      # ← svc.args (if set, space-split)
          # resources, env — same as Deployment
```

### CronJob: `{output_dir}/{name}-cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cleanup
  namespace: production
  labels:
    app: cleanup
spec:
  schedule: "*/5 * * * *"                    # ← svc.schedule
  concurrencyPolicy: Forbid                  # ← svc.concurrencyPolicy
  suspend: false                             # ← svc.suspend (omit if false)
  successfulJobsHistoryLimit: 3              # ← svc.successfulJobsHistoryLimit
  failedJobsHistoryLimit: 1                  # ← svc.failedJobsHistoryLimit
  startingDeadlineSeconds: 300               # ← svc.startingDeadlineSeconds (omit if null)
  jobTemplate:
    spec:
      backoffLimit: 3                        # ← svc.backoffLimit
      activeDeadlineSeconds: 600             # ← svc.activeDeadlineSeconds (omit if null)
      ttlSecondsAfterFinished: 3600          # ← svc.ttlSecondsAfterFinished
      template:
        spec:
          restartPolicy: Never               # ← svc.restartPolicy
          containers:
            - name: cleanup
              image: cleanup-tool:latest
              command:
                - sh
                - -c
                - "python cleanup.py --age=30d"
              # resources, env — same as Deployment
```

### ConfigMap/Secret: Same as Deployment

If `svc.envVars` contains hardcoded/variable → `{name}-config.yaml`
If `svc.envVars` contains secret → `{name}-secrets.yaml`

### NO Service generated

Jobs and CronJobs never get a Service (port is hidden in the UI).

---

## Key Differences from Deployment

| Feature | Deployment | Job | CronJob |
|---------|-----------|-----|---------|
| Replicas | User-defined | N/A (completions/parallelism) | N/A |
| Port / Service | Always | Never | Never |
| Health probes | User-defined | Never | Never |
| Volumes | User-defined | Hidden | Hidden |
| Init containers | User-defined | Hidden | Hidden |
| Dependencies | User-defined | Hidden | Hidden |
| Command/Args | Not shown | Required | Required |
| restartPolicy | Always (default) | Never/OnFailure | Never/OnFailure |
| Scheduling | N/A | N/A | cron expression |
| Concurrency | N/A | N/A | Allow/Forbid/Replace |
| TTL cleanup | N/A | Yes | Yes (per job) |

---

## CronJob Manifest Structure

Note the **nesting**: CronJob → jobTemplate → spec → template → spec → containers.

```
CronJob.spec
  ├── schedule, concurrencyPolicy, suspend     ← CronJob-level
  ├── successfulJobsHistoryLimit, failedJobsHistoryLimit
  ├── startingDeadlineSeconds
  └── jobTemplate.spec
        ├── backoffLimit, completions, parallelism  ← Job-level
        ├── activeDeadlineSeconds
        ├── ttlSecondsAfterFinished
        └── template.spec                          ← Pod-level
              ├── restartPolicy
              └── containers[]
```

---

## Implementation Status

### ✅ Fully implemented — no gaps:

**Translator** (`wizard_state_to_resources` Job/CronJob branch):
- All Job fields: command, args, restartPolicy, backoffLimit, completions,
  parallelism, activeDeadlineSeconds, ttlSecondsAfterFinished
- All CronJob fields: schedule, concurrencyPolicy, suspend,
  successfulJobsHistoryLimit, failedJobsHistoryLimit, startingDeadlineSeconds
- No Service generation (is_job check)

**Generator** (`generate_k8s_wizard`):
- Job branch: flat job_spec with all fields, restartPolicy on pod template
- CronJob branch: nested jobTemplate structure, all CronJob-level fields
- `_build_pod_template`: command/args override for main container

### ❌ No gaps found.
