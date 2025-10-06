# Endpoint Persistence using Network Volume and CDR

## Definitions

- Worker: docker container that relies on their local sandbox environment `/app` for all of its operations.

- Volume: network volume attached to a Worker as provisioned by its parent Endpoint.

- Workspace: designated environment residing in the network volume `/runpod-volume/runtimes/{endpoint_id}`. Serves as an Endpoint persistence disk.

- CDR: continuous data replication daemon that ensures data is replicated to the network volume workspace with an optional "hydrate" function (data transfers from volume to container)

## Logic

- First container boots, and checks for volume presence and endpoint workspace. Create if not found.

   1. Container will proceed to download any system or python dependencies in parallel as instructed from the remote decorator.

   2. Container runs its job.

   3. Container launches its own CDR daemon to monitor `/app` for changes and replicates `/app` to `/runpod-volume/runtimes/{endpoint_id}` as files are downloaded or changed.

- Subsequent container boots, and checks for volume presence and endpoint workspace. Found.

   1. Container launches its own CDR daemon to hydrate its `/app` from the workspace and then watch `/app` for changes.

   2. Container completely skips downloading from the internet.

   3. Container runs its job.

### Logic Flow
```mermaid
graph TD
      A[Container Boot] --> B{Volume Present?}
      B -->|No| C[Use Local /app Only]
      B -->|Yes| D{Workspace Exists?}

      D -->|No| E["Create Workspace<br/>/runpod-volume/runtimes/{endpoint_id}"]
      D -->|Yes| F[Workspace Found]

      E --> G[Launch CDR Daemon<br/>Monitor /app → Workspace]
      F --> H{First Container?}

      H -->|Yes| I[Launch CDR Daemon<br/>Monitor /app → Workspace]
      H -->|No| J[Launch CDR Daemon<br/>Hydrate /app ← Workspace<br/>Then Monitor /app →
  Workspace]

      G --> K[Download Dependencies<br/>System + Python]
      I --> K
      J --> L[Skip Downloads<br/>Use Cached Data]

      K --> M[CDR: Replicate Downloads<br/>/app → Workspace]
      L --> N[Execute Job]
      M --> O[Execute Job]

      O --> P[CDR: Continue Monitoring<br/>/app → Workspace]
      N --> Q[CDR: Continue Monitoring<br/>/app → Workspace]

      C --> R[Execute Job<br/>No Persistence]

      style A fill:#e1f5fe,color:#000000
      style G fill:#f3e5f5,color:#000000
      style I fill:#f3e5f5,color:#000000
      style J fill:#fff3e0,color:#000000
      style K fill:#e8f5e8,color:#000000
      style L fill:#fff9c4,color:#000000
      style M fill:#fce4ec,color:#000000
      style P fill:#fce4ec,color:#000000
      style Q fill:#fce4ec,color:#000000
```