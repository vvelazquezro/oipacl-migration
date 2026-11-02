# GSAP application onboarding instructions for coding assistants

Copy this file into the application repository as `AGENTS.md`, or provide it to another coding assistant as project instructions. Use it when preparing or changing an app for GSAP. The [human onboarding guide](https://collaborate.akamai.com/confluence/spaces/GSAP/pages/1415079472/Onboarding+Your+App) is the source of truth if a platform requirement changes.

## Goal

Prepare an app that builds locally and runs as **two stateless replicas** at `https://gsap.akamai.com/<app-path>/`. Finish with recorded test results and a ready-to-paste GSAP Jira Story. Ask the owner for missing facts; do not invent them or report an unrun test as passed.

## Work in this order

1. **Collect the onboarding facts.** Identify the app name, purpose, owning team, technical contact, Git repository URL and branch, public/private status, Dockerfile path, framework, start command, routes, assets, API calls, environment variables, filesystem writes, expected traffic and resource use, scheduled work, and external services. The standard automated mirror uses an externally reachable GitHub repository; ask the GSAP team before using another host. Internal `bits.linode` and `git.source` repositories are not supported. For a private repository, prompt the owner to prepare a fine-grained personal access token with no expiration, limited to this repository and `Contents: Read-only`. Have the owner hand it off through PrivBin in step 8. Confirm these facts or mark them as open questions before implementation.
2. **Agree on a unique path.** Ask the owner for the requested path and have them check paths already in use at `https://gsap.akamai.com/logs`. Make pages, assets, refreshed deep links, redirects, and API calls work under `/<app-path>/`. Configure build-time frontend paths before building the image; a runtime variable cannot rewrite already-built asset URLs. Confirm the assigned path works locally, not only `/`.
3. **Implement identity and access.** GSAP signs in `akamai.com` users with Google and forwards their email in `X-Auth-Request-Email` on protected requests. Read the header server-side and enforce the app's own email allowlist or roles on every protected request. Deny protected requests when the header is missing or the user is not allowed. Trust the header only behind the GSAP-protected Gateway; remove direct public routes and development identity bypasses before deployment. Confirm the access policy with the owner.
4. **Build the container and declare configuration.** Provide a Dockerfile that installs dependencies, copies/builds the app, and starts it on plain HTTP at `0.0.0.0:8080`; a single container is preferred. Discuss Docker Compose or Helm needs with GSAP before submission. Use Dockerfile `ENV` for non-secret defaults that the app actually reads. Identify every deployment-specific variable, separating non-secret values from runtime secrets. Keep passwords, database URLs with credentials, API tokens, and access keys out of source, Dockerfile `ENV`/`ARG`, and images. Confirm the image builds and starts locally.
5. **Provide readiness and liveness endpoints.** Provide fast, unauthenticated `GET` paths on port `8080` for both APL Workload probes, preferably separate endpoints such as `/readyz` and `/livez`. Kubernetes probes the pod IP and container port directly, so these paths do not need the public `/<app-path>/` prefix. The names are examples, not required paths. Readiness returns `200` only when this pod can serve requests, including required initialization and dependencies; otherwise it fails, for example with `503`. Liveness returns `200` while the app process is responsive and fails only when a restart is likely to help; a brief database or external API outage must not trigger a restart loop. If one endpoint serves both probes, verify it accurately represents both conditions. Ask for the expected startup time. Record the exact paths and purposes so GSAP can configure both APL Workload probes. Separately identify a path the app serves without app-level sign-in through the exposed Service route for APL's availability check; it may need the public prefix and must be allowed by the Service's URL paths. Tell GSAP if Gateway authentication protects it so a safe probe can be arranged. Do not use a login redirect or Dockerfile `HEALTHCHECK` as a substitute.
6. **Plan shared state.** Inspect uploads, local databases, access lists, generated files, caches, and `/data` or other filesystem writes. Each of GSAP's two replicas has a separate, temporary filesystem. Use a private Object Storage bucket through its S3-compatible API for durable files or snapshots, or PostgreSQL for transactional shared state. A persistent volume is an exception to discuss with GSAP. For Object Storage, ask whether the app owner or GSAP will provision the bucket/key; record expected growth, retention, and backup owner. For managed PostgreSQL, request app-specific access from GSAP, use a runtime `DATABASE_URL` with TLS, and test locally against a local PostgreSQL instance with the normal migrations. Confirm whether data saved through one replica can be read through the other.
7. **Verify locally.** Build and run the final image. Test `http://localhost:8080/<app-path>/`, a refreshed deep link, assets, redirects, and an API action. Request readiness and liveness paths without following redirects and confirm each returns HTTP `200` while healthy. If a required dependency is unavailable, verify readiness fails while liveness still reports a responsive process. Test allowed and denied access with and without a local `X-Auth-Request-Email` header. Restart the container and check durable data. If the app saves shared state, run two containers against the same store, write through one, and read through the other. For PostgreSQL, test migrations plus reads and writes using local credentials and data. Record each result and any test you could not run.
8. **Prompt the owner to hand off secrets.** Ask whether the app or private repository needs any secrets. If so, instruct the owner to put each **secret name and value**, including the repository token, in [PrivBin](https://privbin.akam.ai/), the internal temporary secret store, and put the retrieval link in the Jira Story. Do not ask for secret values or the bearer retrieval link in assistant chat. In the generated ticket, include the secret variable names and a clear `[paste PrivBin link directly into Jira]` field for the owner. If the link expires before GSAP retrieves it, have the owner create a new entry and update the ticket. If no secrets are needed, state `None`. GSAP will place supplied secrets in the workload's APL-managed runtime Secret.
9. **Prepare the Jira handoff.** Ask the owner for any remaining ticket facts. Produce a copy-ready **Story title and description** using every field below, with actual values and evidence where known and `TBD` where the owner must supply information. Link to the [GSAP Jira project](https://track.akamai.com/jira/projects/GSAP/). Do not create or submit the ticket unless the owner separately asks you to. The owner must paste the PrivBin retrieval link into the ticket before submitting it.

## Required final output

First give a brief account of code changes, tests run, and unresolved blockers. Then provide a Jira Story that the owner can copy and paste. Include all of these fields, even if the value is `None`, `Not tested`, or `TBD`:

```text
Issue type: Story
Project: GSAP
Create ticket: https://track.akamai.com/jira/projects/GSAP/
Summary: Onboard <app name> at /<app-path>/

App and owner: <name, team, technical contact, short purpose>
Repository: <URL, branch, public/private status, Dockerfile path>
Requested path: /<app-path>/
Health: <readiness path and condition, liveness path and condition, expected startup time, exposed Service availability path, local HTTP results>
Sign-in and access: <all signed-in akamai.com users or app-specific allowlist/roles>
Configuration: <non-secret environment variable names and values>
Secrets: <secret variable names only; [paste PrivBin link directly into Jira] or None>
State and storage: <filesystem writes, shared store, storage provisioner, expected growth, retention, backup owner>
Resources: <expected CPU, memory, request/job duration, scheduled work>
External integrations: <APIs, destinations, firewall or fixed-source-IP needs, or None>
Local test results: <image build/run, assigned path and deep link, assets/API, health, access, restart, two-instance shared state, local PostgreSQL/migrations when applicable>
Platform requests or exceptions: <managed PostgreSQL, GSAP-owned bucket, Docker Compose/Helm, long-running work, PVC, or None>
Open questions or blockers: <specific remaining items or None>
```

For any change after deployment, explain that the Gitea mirror checks the source repository approximately every 10 minutes, Tekton builds a new image, Harbor stores it, and APL rolls it out after a successful build. Mirror, build, and rollout are separate stages. Direct the owner to `https://gsap.akamai.com/logs/<your-app>` to check each stage. Changes to GSAP-managed routes, runtime variables, or Secrets go through [GSAP Support](https://collaborate.akamai.com/confluence/spaces/GSAP/pages/1539017888/GSAP+Support).

## Guardrails

- Use test credentials locally and keep secret values and PrivBin retrieval links out of source, images, logs, and assistant output. Put the retrieval link only in the Jira ticket.
- Keep readiness, liveness, and Service availability paths usable without a user session. A protected root URL or login redirect is not a health check.
- Treat local container files as temporary and private to one replica. Object Storage is an API, not a mounted `/data` directory.
- Retry transient database connection failures, and keep readiness false when a required database-backed feature cannot initialize.
- Keep CPU and memory modest. Discuss requests or jobs expected to take more than about 10 minutes, and flag external firewall or fixed-source-IP requirements for GSAP review.
- State which onboarding checks passed, failed, or were not run. The handoff is complete only when the Jira draft contains every required field and the owner knows to add the PrivBin link directly in Jira.
