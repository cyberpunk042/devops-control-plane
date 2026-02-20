# Assistant — Scenarios

> Concrete examples of what the assistant panel shows in real situations.
> Each scenario shows the full panel content with hierarchical structure.
>
> Notation:
> - `[]` wraps assistant content for a section/element
> - Indented `[]` wraps content for a nested element within that section
> - `← HOVERED` marks the element currently being hovered
> - Every visible element on the page has a corresponding entry in the panel
> - The assistant TALKS like a helpful colleague, not a reference manual

---

## Scenario 1: Wizard Step 1 — Hovering "development" environment

**Context:** User is on Project Configuration (step 1). All fields are filled in.
User hovers down to the Environments section, specifically over the "development" row.

### Assistant Panel

```
🧙 Welcome to the Setup Wizard
[6 steps to configure your project. Start with your project name —
 it's used across all generated configs and scripts.]

────────────────────────────────

Project Name *
[This is your project's identity — it'll show up in Docker labels,
 CI pipeline names, folder structures, and every generated config.]

Description
[Good to have — it'll appear in your README header, package
 metadata, and repository description when you push.]

Repository
[This connects your project to its Git remote. CI webhooks,
 GitHub integration, and deployments will reference this.]

────────────────────────────────

📂 Domains
[These are logical groupings for your modules. When you add
 modules in step 2, each one belongs to a domain. Think of
 them as folders for organizing your codebase — library for
 shared code, ops for tooling, docs for documentation.]

    Add domain...
    [Type a name and hit + Add if you need another grouping.]

────────────────────────────────

📋 Environments
[Environments scope your secrets and variables. Your project
 config, integrations, and generated files are shared across
 all environments — what changes per environment are the
 secret values and environment variable values.

 So your DB_HOST might be dev-db.internal in development
 but prod-db.example.com in production. Same project config,
 different credentials per environment.

 You've got 2 set up so far.]

    development · default                    ← HOVERED
    [The development environment is where your team builds,
     tests, and iterates. It typically involves:
     • Test credentials and local service endpoints
     • Debug-level settings and verbose output
     • Relaxed security and faster feedback loops

     As the default environment, it will be pre-selected
     when you define secrets and variables in step 3.

     💡 Click the name or description to edit. Use × to remove.]

    production
    [Production environment — live-facing, real credentials
     and hardened settings. Configured separately in step 3.]

    Add environment...
    [Add another deployment target (e.g., staging, qa, preview).
     Each one gets its own secret values in step 3.]
```

---

## Scenario 2: Wizard Step 5 — Hovering Docker integration card

**Context:** User is on Integrations (step 5). System tools show 8/15 available.
Scan is 18h old with file changes detected. Docker is ⚠ not configured with
daemon offline but Dockerfile and docker-compose.yml found. User hovers the
Docker integration card.

**What's visible on the page:**
- Scan bar: 18h ago, files changed — rescan recommended
- System Tools: 8/15 available (missing: bandit, kubectl, mypy, pip-audit, pytest, ruff, safety)
- Tool badges: ✓ docker, docker-compose, gh, git, helm, node, npm, terraform
- File detection: ● docker compose, dockerfile, git repo, github actions, k8s manifests, pages config | ○ package json, pyproject, terraform dir
- Integrations: CI/CD ✓, Docker ⚠, Git ✓, GitHub ✓, Pages ✓
- DevOps Extensions: DNS & CDN (unchecked), Kubernetes ✗ not installed, Terraform ⚠ not configured

### Assistant Panel

```
🧙 Setup Wizard — Step 5 of 6
[You're almost there! This step shows what tools and integrations
 are available on your system. Enable the ones you need, configure
 them, then head to the final review.

 Checked integrations appear as cards in the Integrations and
 DevOps tabs on the dashboard.]

────────────────────────────────

🔄 Scan Status
[Your scan is 18 hours old and files have changed since then.
 Hit Re-Scan to refresh — if you've added or modified config
 files, detection results may be different now.]

────────────────────────────────

🛠️ SYSTEM TOOLS · 8 of 15 available
[These are CLI tools the control plane uses for automation, quality
 checks, and deployment. You've got the core ones (docker, git,
 node, terraform) but some quality and security tools are missing.

 Missing tools won't block you from setting up integrations,
 but they limit what the control plane can automate for you.]

    ✗ bandit
    [Python security scanner — finds common vulnerabilities in
     your code. Useful for production readiness checks.]

    ✗ kubectl
    [Kubernetes CLI — required for the K8s integration below.
     Without it, the control plane can't talk to any cluster.
     This is why Kubernetes shows "not installed" below.]

    ✗ mypy
    [Python type checker — catches type errors before they
     hit runtime. Not required but adds a quality layer to
     your CI pipeline.]

    ✗ pip-audit
    [Scans your Python dependencies for known security
     vulnerabilities. Recommended before any production deploy.]

    ✗ pytest
    [Python test runner — if you want automated testing in
     your CI/CD pipeline, you'll need this installed. Without
     it, the test step in your workflow has nothing to run.]

    ✗ ruff
    [Fast Python linter and formatter. Used in CI quality
     checks. Without it, linting steps get skipped.]

    ✗ safety
    [Dependency vulnerability scanner. Similar to pip-audit
     but checks against a different advisory database.]

    ✓ Tool badges (docker, docker-compose, gh, git, helm, node, npm, terraform)
    [These are the tools that ARE installed. They're what make
     your integrations work — docker for containers, gh for
     GitHub CLI, terraform for infrastructure, etc.]

────────────────────────────────

📋 File Detection
[These show what config files and project structures were found
 in your repository. Green means detected, gray means not found.

 Detected files help integrations pre-fill their setup. For
 example, your Dockerfile lets Docker setup pull your existing
 base image, ports, and CMD instead of starting from scratch.

 You're missing package.json (no Node.js project detected),
 pyproject (no Python packaging), and terraform dir (no .tf
 files yet). That's fine — they'll appear after you configure
 those integrations.]

────────────────────────────────

🔌 INTEGRATIONS
[Your core project integrations. Each checked one will show
 up as a card in the dashboard's Integrations tab.

 The checkbox just controls visibility — unchecking won't
 delete any configuration, just hides it from the UI.]

    ☑ CI/CD · ready ✓
    [Your CI/CD pipeline is set up. GitHub Actions workflow
     is configured and ready to trigger on push. You can
     tweak branches, test commands, or linting through Setup.]

    ☑ Docker · ⚠ not configured              ← HOVERED
    [Docker handles your container builds, multi-service
     orchestration, and compose-based workflows.

     Your project already has a Dockerfile and
     docker-compose.yml — setup can reference those
     to pre-fill your configuration.

     Two ways to set it up:
     • ⚙️ Setup — quick inline form, stays on this page
     • 🚀 Full Setup — 3-step modal wizard with guided
       detection, per-container configuration, and a
       live preview of generated files

     Full Setup is the best path for first-time config
     or multi-container projects.]

        ✗ Docker daemon not reachable
        [The daemon isn't running right now. This just means
         live container status won't be available — setup
         and configuration work fine without it.]

        ✓ Dockerfile
        [Found in your project root. When you run Full Setup,
         it can read your existing base image, exposed ports,
         and CMD to pre-fill the configuration form.]

        ✓ docker-compose.yml
        [Found in your project root. Defines your multi-
         container setup — services, networks, volumes.
         Full Setup will reference this for service names
         and port mappings.]

        ⚙️ Setup
        [Opens a quick inline form right here on the page.
         Good for simple tweaks — base image, port, CMD.
         Stays in the wizard without opening a modal.]

        🚀 Full Setup →
        [Opens the 3-step Docker configuration modal:
         1. Detect — scans running containers and files
         2. Configure — set up each container's details
         3. Preview — see generated Dockerfile and compose

         This is the best path for first-time setup or
         when you have multiple containers to configure.]

    ☑ Git · ready ✓
    [Git integration is configured — your remote is set and
     the control plane can manage branches, commits, and
     push operations through the dashboard.]

    ☑ GitHub · ready ✓
    [GitHub CLI is configured — you get PR management, issue
     tracking, secrets sync to GitHub, and Actions dispatch
     right from the dashboard.]

    ☑ Pages · ready ✓
    [Static site builder is set up with multi-section support.
     Content from your content folders gets published through
     the Pages pipeline.]

────────────────────────────────

⚡ DEVOPS EXTENSIONS
[Advanced infrastructure integrations for production deployments.
 These are optional and go beyond basic project setup.

 Same as above — the checkbox controls dashboard visibility,
 not whether the integration exists.]

    ☐ DNS & CDN · n/a
    [Not enabled. Check this if you need DNS resolution checks
     and CDN management in your dashboard. Requires an external
     provider (Cloudflare, Route53, etc.) to be useful.]

    ☑ Kubernetes · ✗ not installed
    [K8s deployment is enabled in the wizard, but kubectl isn't
     installed on this machine (see System Tools above). Without
     kubectl, the control plane can't deploy to any cluster.

     Install kubectl first, then come back to configure pods,
     services, ingress, and namespace settings through Setup
     or Full Setup.

     Your k8s manifests were detected in file scanning, so
     once kubectl is available, setup can reference those.]

    ☑ Terraform · ⚠ not configured
    [Infrastructure as Code for provisioning cloud resources
     (AWS, GCP, Azure, DigitalOcean, etc.).

     The Terraform CLI is installed (it's in your tools above)
     but no .tf configuration files have been generated yet.
     That's why terraform dir shows as not detected in file
     scanning.

     Use Setup or Full Setup to pick a provider, region, and
     backend — it'll generate your main.tf and variables.]
```

### What this demonstrates

- **Step context always at top** — wizard step 5 of 6, almost done
- **Scan status area** — tells user their scan is stale and what to do
- **System tools section** — each missing tool explained with WHY it matters,
  not just what it is. kubectl links to K8s being broken below. pytest links
  to CI testing being limited.
- **File detection** — explains what detected/not-detected means practically
  and reassures about missing ones
- **Every integration** has context — what it does, what its status means
- **Docker (hovered) gets full depth** — daemon issue explained with fix
  commands, files explained with how setup uses them, both setup paths
  explained with when to use each
- **Cross-references** — kubectl missing → K8s not installed. Terraform CLI
  installed → but no .tf files. File detection → integration setup.
- **DevOps extensions** — each one explained with dependencies and next steps
- **Nothing restated** — doesn't echo badge text or status labels, explains
  what they MEAN and what to DO
- **Conversational tone** — "You're almost there", "That's fine", "This is
  the best path for", "you'll just enter", "once kubectl is available"

---

## Scenario 3: K8s Full Setup Modal — Step 1 (Detect)

**Context:** User clicked Full Setup on the Kubernetes integration card from the
wizard Integrations step. A modal opens showing the K8s detection results.
This is step 1 of the K8s setup wizard — a read-only scan.

**What's visible on the page:**
- Scan bar: just now, Re-Scan
- Info banner: "This is a read-only scan. To configure K8s resources, proceed to Configure."
- Kubernetes Environment: kubectl Not found, Helm Available, Cluster Not connected, Manifests 2 found, Helm Chart None
- Docker Context: Docker Available, Compose file docker-compose.yml, Dockerfiles 5 found
- Compose Services: cli (:8000, application), web (:8001, application), mysql (:3306, infrastructure)
- Registry Context: cyberpunk042/devops-control-plane → ghcr.io/cyberpunk042/devops-control-plane
- Environments: development, production

### Assistant Panel

```
☸️ Kubernetes Setup — Step 1: Detect
[This step scans your system and project to build a picture of
 what's available for Kubernetes deployment. Everything here is
 read-only — nothing gets changed. Review what was found, then
 hit Configure → when you're ready to start building your K8s
 resources.]

────────────────────────────────

🔄 Scan Status
[Just scanned — results are fresh. If you make changes to your
 project files or install new tools, hit Re-Scan to refresh.]

ℹ️ Read-only scan
[This step only reads — it won't modify any files or create any
 resources. Configuration happens in the next step.]

────────────────────────────────

📊 Kubernetes Environment
[This shows the K8s tooling and cluster connectivity available
 on your machine right now. It's the foundation for what you
 can do with Kubernetes: generate manifests, deploy to clusters,
 or manage releases with Helm.

 You've got Helm and some existing manifests, but no kubectl
 and no cluster connection — so you can generate and prepare
 K8s resources, but deploying them will need kubectl set up
 later.]

    kubectl · Not found
    [kubectl is the CLI that communicates with Kubernetes
     clusters. Not having it doesn't block you from
     configuring and generating manifests — it just means
     you can't deploy directly from the control plane yet.

     When you're ready: brew install kubectl, apt install
     kubectl, or download from kubernetes.io.]

    Helm · Available
    [Helm is installed — it's a package manager for K8s
     that bundles your manifests into reusable charts.
     In Configure, you can choose between raw manifests
     or Helm chart output.]

    Cluster · Not connected
    [No active cluster connection right now. This goes
     hand-in-hand with kubectl not being installed — once
     kubectl is set up and pointed at a cluster (via
     kubeconfig), this will show your cluster details.]

    Manifests · 2 found
    [2 existing K8s manifest files found in your project.
     Configure can use these as a starting point instead
     of generating everything from scratch.]

    Helm Chart · None
    [No Helm chart structure found. If you choose Helm
     output in Configure, one will be generated for you.]

────────────────────────────────

🐳 Docker Context
[This is the container infrastructure that feeds into K8s.
 Kubernetes runs containers, so your Docker setup directly
 determines what gets deployed.

 Your Docker environment is healthy — engine available,
 compose file defining your services, and 5 Dockerfiles
 ready to build images from.]

    Docker · Available
    [Docker engine is accessible — container builds will
     work when you're ready to build and push images to
     your registry.]

    Compose file · docker-compose.yml
    [Your compose file is the bridge between Docker and K8s.
     The services defined here are what the control plane
     turns into Kubernetes Deployments and Services.]

    Dockerfiles · 5 found
    [5 Dockerfiles across your project — each one can
     produce a container image that K8s will run as a pod.]

────────────────────────────────

📦 Compose Services
[These are the services from your docker-compose.yml, classified
 by what they do.

 The control plane looks at each service and categorizes it:
 • Application services → become K8s Deployments with their
   own pods, replicas, and service endpoints
 • Infrastructure services → databases, caches, queues —
   these need special handling in K8s

 You've got 2 application services and 1 infrastructure service.
 This classification drives how Configure builds your K8s
 resources in the next step.]

    🚀 cli · builds locally · :8000 · application
    [Your CLI service — builds from a local Dockerfile and
     listens on port 8000. In Configure, this becomes a K8s
     Deployment. You'll set replicas, resource limits, health
     checks, and how the service is exposed.]

    🚀 web · builds locally · :8001 · application
    [Your web service — builds locally, port 8001. Also becomes
     a K8s Deployment. Port 8001 will map to a K8s Service
     for routing traffic to it.]

    🐬 mysql · mysql · :3306 · infrastructure
    [Database service running MySQL on port 3306. Infrastructure
     services need a different approach in K8s:
     • StatefulSet — runs MySQL in the cluster with persistent
       storage. Good for dev, more complex for production.
     • Managed service — use a cloud database (RDS, Cloud SQL,
       Azure Database). Simpler operations, costs money.
     • Skip — handle the database outside of K8s entirely.

     You'll make this choice in Configure.]

    💡 Service mapping
    [2 application services will become K8s Deployments.
     The infrastructure service (mysql) gets its own decision
     point in Configure — StatefulSet, managed, or skip.]

────────────────────────────────

🏷️ Registry Context
[This is where your container images live. When K8s needs to
 run your services, it pulls images from this registry.

 The registry URL is derived from your GitHub repository —
 images built from your Dockerfiles get pushed to GitHub
 Container Registry (ghcr.io) and K8s pulls them from there.]

    Repository · cyberpunk042/devops-control-plane
    [Your GitHub repository — the source of truth for your
     code and the basis for image naming.]

    Registry · ghcr.io/cyberpunk042/devops-control-plane
    [GitHub Container Registry. Your built images land here.
     K8s pods will reference images like:
     ghcr.io/cyberpunk042/devops-control-plane/web:latest

     If this registry is private, you'll need to configure
     image pull secrets in K8s — Configure handles that.]

────────────────────────────────

🌍 Environments
[Your deployment environments from the project wizard. In
 Configure, each environment can get its own K8s configuration —
 different replica counts, resource limits, namespaces, or
 ingress rules.

 This is where environments and K8s meet: same application
 code, different operational settings per environment.]

    ⭐ development
    [Development K8s config — typically fewer replicas, lower
     resource limits, and more permissive settings for fast
     iteration.]

    🔑 production
    [Production K8s config — more replicas for availability,
     higher resource limits, stricter health checks, and
     production-grade monitoring.]
```

### What this demonstrates

- **Modal context** — K8s Setup step 1, read-only scan
- **Every section has explanatory content** — not just restating statuses
  but explaining what they mean for the user's K8s journey
- **Docker ↔ K8s relationship** — explains how compose services become
  K8s deployments, how Dockerfiles produce images K8s runs
- **Infrastructure service decision** — mysql gets a detailed explanation
  of the three options (StatefulSet, managed, skip) so the user knows
  what's coming in Configure
- **Registry explained practically** — shows example image URL, mentions
  pull secrets if private
- **Environments in K8s context** — same environments from the wizard,
  now explained as operational configuration targets
- **Cross-references throughout** — kubectl ↔ cluster connection,
  compose services ↔ K8s deployments, Dockerfiles ↔ container images
- **No overreaction** — kubectl missing is explained matter-of-factly,
  not as a crisis. You can still configure and generate.

---

## Scenario 4: K8s Full Setup Modal — Step 2 (Configure)

**Context:** User proceeded from Detect to Configure. This is the big one —
every compose service becomes a K8s deployment or infrastructure resource,
with deep nested configuration. The cli service card is fully expanded.

**What's visible on the page:**
- Step bar: ✓ Detect → ② Configure → ③ Review & Apply
- Application Deployments: cli (expanded, fully configured), web (collapsed)
- Infrastructure Services: mysql (StatefulSet with env vars)
- Cluster Settings: namespace, output dir, Skaffold, Helm

### Assistant Panel

```
☸️ Kubernetes Setup — Step 2: Configure
[This is where you build your K8s resources. Each service from
 your Docker Compose gets turned into Kubernetes manifests —
 Deployments for applications, StatefulSets for databases.

 Everything you set here goes into your manifest files in the
 next step. Take your time — this is the heart of your K8s
 configuration.]

════════════════════════════════

📦 Application Deployments
[2 services from your docker-compose.yml were classified as
 applications. Each one becomes a K8s Deployment — a set of
 pods running your container with replica management, health
 monitoring, and rolling updates.

 Check the ones you want to deploy. Uncheck to skip.]

────────────────────────────────

    ☑ cli · local build · :8000 · Deployment
    [Your CLI service — it builds from a local Dockerfile,
     listens on port 8000, and will run as a K8s Deployment.
     Everything below configures how this service runs in
     your cluster.]

        Container Image
        [The full image reference K8s will pull when creating
         pods. This was derived from your registry context
         (ghcr.io) + your service name. Make sure this matches
         what your CI pipeline pushes.]

        Port
        [The port your container listens on inside the pod.
         This must match what your application actually binds
         to — it comes from your compose port mapping.]

        Replicas
        [How many copies of this pod run simultaneously.
         2 means you get basic high availability — if one pod
         crashes, the other keeps serving while K8s restarts
         the failed one. Scale up for more traffic capacity.]

        Service Type
        [How this service is exposed within or outside the
         cluster.
         • ClusterIP — internal only, pods in the cluster
           can reach it. Use kubectl port-forward for local
           dev access.
         • NodePort — exposes on each node's IP at a fixed
           port. Simple but less flexible.
         • LoadBalancer — provisions an external load balancer
           (cloud providers only). Use for public-facing
           services.]

        Update Strategy
        [Controls how K8s rolls out new versions of your pods.]

            RollingUpdate
            [Replaces pods gradually — new ones come up before
             old ones go down, so there's no downtime.]

            Max Surge
            [How many extra pods can exist during an update.
             1 means at most 3 pods during a rollout of 2
             replicas — the extra one comes up before an old
             one goes down.]

            Max Unavailable
            [How many pods can be down during an update.
             1 means at least 1 pod is always running, even
             mid-rollout. Set to 0 for zero-downtime deploys
             (but rollouts take longer).]

        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

        ▸ Resource Limits · ⚠ BestEffort
        [Resource limits tell K8s how much CPU and memory your
         pod needs (request) and how much it's allowed to use
         (limit). This determines scheduling, quality of
         service, and what happens under pressure.

         Right now you're at BestEffort QoS — that means K8s
         will evict these pods first if the node runs low on
         resources. Set both requests AND limits to get
         Guaranteed QoS.]

            REQUEST (Guaranteed Minimum)
            [The minimum resources K8s reserves for your pod.
             The scheduler uses this to decide which node to
             place the pod on. Your pod is guaranteed at least
             this much.]

                CPU · 100m
                [100 millicores = 10% of one CPU core. That's
                 a light workload. Sufficient for a CLI service
                 that isn't constantly processing.]

                Memory · 128Mi
                [128 megabytes reserved. If your app typically
                 uses more than this at rest, increase it —
                 going under request means K8s might evict you
                 under memory pressure.]

            LIMIT (Hard Ceiling)
            [The maximum your pod can use. If it exceeds CPU
             limit, it gets throttled. If it exceeds memory
             limit, it gets OOM-killed — the pod restarts.]

                CPU · 500m
                [500 millicores = half a CPU core max. Gives
                 headroom for spikes above the 100m request.]

                Memory · 256Mi
                [256 megabytes max. If your app leaks memory
                 or handles a large request, it'll be killed
                 and restarted at this threshold.]

            QoS Class → ⚠ BestEffort
            [Kubernetes assigns a Quality of Service class
             based on your resource settings:
             • Guaranteed — request = limit for all resources.
               Highest priority, last to be evicted.
             • Burstable — request < limit. Middle priority.
             • BestEffort — no limits set on some resources.
               First to be evicted under pressure.

             To move from BestEffort to Burstable or
             Guaranteed, make sure all containers have both
             request and limit set.]

        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

        ▸ Health Checks · recommended
        [Health checks let K8s know if your pod is working
         properly. Without them, K8s only knows if the
         container process is running — not whether your
         application is actually responding.

         Two types work together:
         • Readiness — is the pod ready to receive traffic?
         • Liveness — is the pod still alive, or stuck?]

            ☑ Readiness Probe
            [K8s sends traffic to a pod only after its
             readiness probe passes. If it starts failing,
             the pod is removed from the service — no more
             traffic until it recovers.

             Good for: slow boot apps, dependency waits.]

                HTTP GET
                [The probe type. HTTP GET hits an endpoint
                 and expects a 200-399 response. Other options:
                 TCP (just connects), Exec (runs a command).]

                Path · /health
                [The HTTP endpoint K8s hits. Your app needs to
                 respond at this path — a simple 200 OK is
                 enough. If this endpoint doesn't exist, every
                 probe will fail and K8s won't send traffic.]

                Port · 8000
                [Which port to probe. Should match your app's
                 listening port.]

                Delay (s) · 5
                [Seconds to wait after the container starts
                 before the first probe. Give your app enough
                 time to boot — too low and the probe fails
                 during startup.]

                Period (s) · 5
                [How often K8s runs the probe. 5 seconds means
                 K8s checks every 5 seconds. Lower = faster
                 detection but more load on the endpoint.]

                Timeout (s) · 3
                [How long to wait for a response before counting
                 the probe as failed. If your /health endpoint
                 is slow, increase this.]

            ☑ Liveness Probe
            [If the liveness probe fails repeatedly, K8s
             kills and restarts the pod. This catches deadlocks,
             infinite loops, and zombie processes that are
             technically running but not functioning.

             Be careful with liveness — aggressive settings
             can cause restart loops if your app is just slow.]

                HTTP GET · /health · :8000
                [Same endpoint as readiness. This is common —
                 one /health route serves both probes.]

                Delay (s) · 10
                [Higher than readiness — gives the pod time to
                 pass readiness first before liveness checks
                 begin. Prevents kill-during-boot scenarios.]

                Period (s) · 15
                [Checks every 15 seconds. Less aggressive than
                 readiness — you don't want to restart pods
                 over brief slowdowns.]

                Failures · 3
                [How many consecutive failures before K8s
                 restarts the pod. 3 × 15s = 45 seconds of
                 failures before action. Gives your app time
                 to recover from temporary issues.]

        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

        ▸ Environment Variables
        [Environment variables injected into your container at
         runtime. These are how your app gets configuration —
         database URLs, API keys, feature flags, etc.]

            ⚠ Multi-env project
            [You have multiple environments (development,
             production). Values shown here are defaults.
             Use Variable or Secret injection type for values
             that should differ across environments — the
             actual values come from your environment's
             .env file at deploy time.]

            CONTENT_VAULT_ENC_KEY · Secret
            [Injected as a Kubernetes Secret reference. The
             actual value comes from ${CONTENT_VAULT_ENC_KEY}
             in your environment's .env file. It's never
             hardcoded in the manifest — K8s pulls it from
             the Secret object at deploy time.]

            test · Hardcoded
            [A hardcoded value — this goes directly into the
             manifest as-is, same across all environments.
             Use hardcoded for values that don't change
             between dev and production.]

            + Add variable
            [Add more env vars. Choose the injection type:
             • Hardcoded — same value everywhere
             • Variable — resolved from .env per environment
             • Secret — stored as K8s Secret, never in plaintext]

        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

        ▸ Volume Mounts
        [Volumes give your pod persistent storage that survives
         container restarts. Without volumes, all data inside
         a container is lost when it stops.

         You've got 1 PVC configured.]

            ☑ PVC (dynamic)
            [A Persistent Volume Claim — K8s dynamically
             provisions storage for you. The cluster's storage
             class handles the actual backend (SSD, network
             disk, distributed storage, etc.).]

                PVC Name · my-data
                [A name for this volume claim. Pods reference
                 it by this name internally.]

                Mount Path · /var/lib/data
                [Where the volume appears inside your container.
                 Your app reads/writes to this path and the
                 data persists across restarts.]

                Size · 5Gi
                [5 gigabytes of storage. Can be resized later
                 if the storage class supports expansion —
                 but it's easier to start with enough.]

                Access Mode · ReadWriteOnce
                [Only one node can mount this volume at a time.
                 Fine for single-replica pods or pods that
                 always land on the same node.
                 • ReadWriteOnce — one node read/write
                 • ReadOnlyMany — many nodes read-only
                 • ReadWriteMany — many nodes read/write
                   (requires storage class support like NFS)]

                Storage Class · longhorn
                [Longhorn is a distributed block storage system
                 for K8s. It replicates your data across nodes
                 for resilience — if a node goes down, your
                 data is still available on other nodes.]

                    🐂 Longhorn Settings
                    [Storage-class specific settings for Longhorn.
                     These control how your data is replicated
                     and accessed.]

                        Replicas · 3
                        [Your data is replicated across 3 nodes.
                         You can lose 2 nodes and still have your
                         data intact. Higher = more resilient but
                         uses more disk space across the cluster.]

                        Data Locality · Best-effort
                        [Longhorn tries to keep one replica on the
                         same node as your pod for faster reads.
                         Best-effort means it tries but doesn't
                         guarantee it — strict would fail scheduling
                         if it can't place the data locally.]

            + Add volume
            [Add more volumes — PVCs for persistent data, or
             emptyDir for temporary scratch space that pods
             share between containers.]

        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

        Depends on
        [Service dependencies — if your cli service needs
         another service to be running before it starts,
         check it here. This affects Init Container generation
         and pod startup ordering.]

            ☐ mysql
            [If checked, an init container can be added to
             wait for mysql to be reachable before your cli
             pod starts accepting traffic.]

        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

        ▸ Init Containers · 1
        [Init containers run to completion before your main
         container starts. They're one-shot tasks — migrations,
         permission fixes, dependency checks. If an init
         container fails, K8s retries it until it succeeds
         (the main container never starts until all inits pass).]

            Quick-add buttons
            [Pre-built init container templates:
             • Wait for TCP — waits until a TCP port is open
             • Wait for HTTP — waits for an HTTP 200 response
             • Run migrations — runs DB migration commands
             • Fix permissions — chown/chmod on volume paths
             • Custom — blank container you configure yourself]

            1. wait-for-http
            [Waits for an HTTP endpoint to return 200 before
             your main container starts. Useful for ensuring
             databases, APIs, or other services are ready.]

                Image · curlimages/curl:latest
                [A minimal image with curl installed — just
                 enough to make HTTP requests. Lightweight and
                 commonly used for health checks in init.]

                Command · sh -c
                [The shell command that runs. Typically a loop
                 that curls an endpoint until it responds.
                 Edit the full command to target the specific
                 URL and retry logic you need.]

        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

        ▸ Sidecar Containers · 1
        [Sidecars run alongside your main container in the same
         pod. They share the pod's network and can share volumes.
         Common uses: log collection, metrics export, auth
         proxies, config reloading.]

            Quick-add buttons
            [Pre-built sidecar templates:
             • Log forwarder — ships logs to a central system
             • Config reloader — watches config changes
             • Metrics exporter — Prometheus metrics scraping
             • Auth proxy — OAuth2/OIDC authentication
             • Cloud SQL Proxy — Google Cloud database access
             • Vault agent — HashiCorp Vault secret injection
             • Custom — blank sidecar you configure yourself]

            1. log-forwarder
            [Fluent Bit runs alongside your app and forwards
             logs to wherever you need — Elasticsearch, Loki,
             CloudWatch, etc.]

                Image · fluent/fluent-bit:2.2
                [Fluent Bit — lightweight log processor and
                 forwarder. Much smaller than Fluentd, handles
                 most log shipping needs.]

                ☑ Native sidecar (K8s ≥ 1.28)
                [Uses K8s native sidecar support — the sidecar
                 has a proper lifecycle tied to the pod. It
                 starts before the main container and stops
                 after it. Requires K8s 1.28 or newer.]

                Shared volume · shared-logs → /var/log/app
                [A shared volume between your app and the
                 sidecar. Your app writes logs to /var/log/app,
                 Fluent Bit reads from the same path. This
                 is how they communicate without the network.]

        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

        ▸ Service Mesh
        [A service mesh adds a proxy sidecar to every pod
         that handles traffic management, security (mTLS),
         and observability — without changing your app code.]

            ☑ Enable sidecar injection · Istio
            [Istio is enabled. The Envoy proxy sidecar gets
             injected by the cluster automatically — it's not
             defined in your manifest. The control plane just
             adds the right annotations so Istio knows to
             inject it.]

            ℹ️ Cluster-managed injection
            [The proxy isn't in your manifest. Istio's webhook
             intercepts pod creation and injects the sidecar.
             You only control resource limits and configuration
             here — the actual proxy image and version come
             from your Istio installation.]

            Proxy Resources
            [CPU and memory for the Envoy proxy sidecar.
             These are separate from your app's resources —
             the proxy consumes its own CPU and memory.

             Default values are usually fine for medium traffic.
             Increase limits if you see proxy throttling in
             Istio metrics.]

                CPU Request · 100m / Limit · 500m
                [Proxy CPU — 100m baseline, can burst to 500m.
                 The proxy handles all inbound and outbound
                 traffic for your pod, so under heavy load it
                 needs room to breathe.]

                Mem Request · 128Mi / Limit · 256Mi
                [Proxy memory — Envoy caches routing tables
                 and connection state. 128Mi is fine for most
                 services. Large service meshes with many
                 routes may need more.]

            ▼ Advanced
            [Fine-tuning for the Istio proxy. Usually not
             needed unless you have specific traffic patterns
             or debugging needs.]

                Exclude inbound ports
                [Ports that bypass the proxy entirely for
                 inbound traffic. Useful for health checks
                 or metrics endpoints that don't need mesh
                 encryption.]

                Exclude outbound ports
                [Ports that bypass the proxy for outbound
                 connections. Common: database ports like 3306
                 that go to managed services outside the mesh.]

                Log level · warning
                [Proxy log verbosity. Warning shows only
                 problems. Set to info or debug when
                 troubleshooting mesh routing issues —
                 but debug is very verbose.]

        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

        ▸ Move into another pod...
        [Advanced: moves this container into another pod
         definition. Useful when you want two services to
         share the same pod (same network, same volumes)
         instead of running as separate Deployments.]

════════════════════════════════

🏗️ Infrastructure Services
[Infrastructure services are databases, caches, queues — things
 that store data and need special handling in K8s. Unlike
 application Deployments, they need stable network identities
 and persistent storage.

 1 infrastructure service detected from your compose file.]

────────────────────────────────

    mysql · mysql · :3306 · StatefulSet
    [MySQL was automatically classified as infrastructure
     because it's a database image. StatefulSet was chosen
     because databases need stable identity (each pod gets
     a persistent hostname) and per-pod storage (data stays
     with the pod, even across restarts).

     The alternative options are:
     • Managed — use a cloud database (RDS, Cloud SQL, etc.)
       instead of running MySQL in K8s. Simpler ops.
     • Skip — handle the database entirely outside K8s.]

        ▸ Environment Variables
        [MySQL needs these to initialize the database on first
         run. The ⚠ warnings mean these secrets and variables
         don't exist in your .env file yet — "Create on
         execution" means they'll be created when you deploy.]

            MYSQL_DATABASE · Variable
            [The name of the database to create on first boot.
             Variable type means this comes from your .env file
             and can differ per environment.]

            MYSQL_PASSWORD · Secret
            [Password for the regular MySQL user. Stored as a
             K8s Secret — never in plaintext in your manifests.
             Use Generate to create a strong random password.]

            MYSQL_ROOT_PASSWORD · Secret
            [The root password. Keep this separate from the
             regular user password. Also stored as a K8s Secret.
             You'll rarely use root directly — it's for admin
             operations.]

            MYSQL_USER · Variable
            [The regular database user your application connects
             as. Variable type — can be different per environment
             if needed.]

            + Add variable
            [Add more MySQL env vars if your setup needs them —
             like MYSQL_PORT, custom init scripts, or replication
             settings.]

        ▸ Persistent Storage
        [MySQL needs persistent storage — otherwise your data
         disappears when the pod restarts. Configure the PVC
         size, storage class, and access mode here.]

    + Add infrastructure service...
    [Add another infrastructure service that isn't from your
     compose file — like Redis, RabbitMQ, or Elasticsearch.
     You can configure it from scratch.]

════════════════════════════════

⚙️ Cluster Settings
[Settings that apply across all your K8s resources — namespace
 isolation, where manifest files go, and optional tooling
 like Ingress, Skaffold, and Helm.]

────────────────────────────────

    Namespace · devops-control-plane-development
    [All resources go into this K8s namespace. Namespaces
     isolate your workloads from other projects in the same
     cluster. The name was derived from your project name +
     default environment.]

    Output Directory · k8s/
    [Where the generated manifest files will be written in
     your project. After Review & Apply, you'll find your
     YAML files here.]

    ☐ Generate Ingress manifest
    [Ingress exposes your services to the outside world with
     HTTP routing rules, SSL termination, and virtual hosts.
     If you're only accessing services internally or through
     port-forward, you can skip this.]

    ☑ Generate Skaffold pipeline
    [Skaffold automates the build → push → deploy workflow.
     It watches your source code, rebuilds images on change,
     and redeploys to your cluster automatically — live-reload
     for containers.

     Your skaffold.yaml will tie together your Dockerfiles
     and K8s manifests so you can run:
     • skaffold dev — continuous development loop
     • skaffold run — one-shot deploy

     Skaffold CLI is detected on your system, so you're
     ready to go.]

────────────────────────────────

    ⎈ Helm
    [Helm packages your K8s manifests into a reusable chart
     with templated values. Instead of raw YAML files, you
     get a chart structure with values.yaml for easy
     per-environment overrides.

     Useful when you deploy the same app to multiple clusters
     or want to share your deployment as a package.
     Not required for simple single-cluster setups.]
```

### What this demonstrates

- **Deep nesting done right** — sub → sub-sub → sub-sub-sub (e.g.,
  Volume Mounts → PVC → Longhorn → Replicas, Data Locality)
- **K8s concepts explained conversationally** — QoS classes, probe
  behavior, StatefulSet vs Deployment reasoning, storage access modes
- **Consequences explained** — "if it exceeds memory limit, it gets
  OOM-killed", "3 × 15s = 45 seconds before action", "you can lose
  2 nodes and still have your data"
- **Decision guidance** — Service Type options explained with when to
  use each, infrastructure handling options, Helm vs raw manifests
- **Multi-env awareness** — explains how Variable/Secret injection
  types relate to environments and .env files
- **No false claims** — doesn't speculate about what fields do,
  explains actual K8s behavior
- **Practical tips** — "start Docker Desktop", "debug is very verbose",
  "easier to start with enough" storage
