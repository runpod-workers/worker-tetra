# Runtime Execution Paths

Worker-tetra now supports **dual-mode runtime** - the same handler can serve both Live Serverless and Flash Deployed Apps without code changes.

## Unified Handler Architecture

Both execution modes use the same `RemoteExecutor` with automatic mode detection:

- **Live Serverless**: Request includes `function_code` or `class_code` → Dynamic execution
- **Flash Deployed**: Request omits code fields → Manifest-based routing to pre-deployed code

## Execution Flow

```mermaid
graph TB
      subgraph CLIENT ["CLIENT REQUEST"]
          A["Client sends request<br/>to RunPod endpoint"]
      end

      subgraph HANDLER ["UNIFIED HANDLER (handler.py / lb_handler.py)"]
          B["maybe_unpack()<br/>Extracts Flash artifacts<br/>if in Flash mode"]
          C["RemoteExecutor.ExecuteFunction()"]
          D{"Detect Mode:<br/>function_code or<br/>class_code present?"}
      end

      subgraph LIVE ["LIVE SERVERLESS PATH"]
          E1["Execute dynamic code<br/>from request"]
          E1 --> F1["FunctionExecutor or<br/>ClassExecutor"]
      end

      subgraph FLASH ["FLASH DEPLOYED PATH"]
          E2["Load flash_manifest.json"]
          E2 --> F2["Lookup function<br/>in registry"]
          F2 --> G2["Import from module"]
      end

      subgraph EXEC ["EXECUTION"]
          H["Execute function<br/>(sync or async)"]
          I["Serialize result<br/>cloudpickle + base64"]
      end

      subgraph RESPONSE ["RESPONSE"]
          J["Return FunctionResponse<br/>to client"]
      end

      A --> B
      B --> C
      C --> D
      D -->|"Yes: Live Serverless"| E1
      D -->|"No: Flash Deployed"| E2
      F1 --> H
      G2 --> H
      H --> I
      I --> J

      style A fill:#1976d2,stroke:#0d47a1,stroke-width:3px,color:#fff
      style B fill:#f57f17,stroke:#e65100,stroke-width:3px,color:#fff
      style C fill:#1976d2,stroke:#0d47a1,stroke-width:3px,color:#fff
      style D fill:#9c27b0,stroke:#6a1b9a,stroke-width:3px,color:#fff
      style E1 fill:#0d7f1f,stroke:#0d4f1f,stroke-width:3px,color:#fff
      style F1 fill:#0d7f1f,stroke:#0d4f1f,stroke-width:3px,color:#fff
      style E2 fill:#1976d2,stroke:#0d47a1,stroke-width:3px,color:#fff
      style F2 fill:#1976d2,stroke:#0d47a1,stroke-width:3px,color:#fff
      style G2 fill:#1976d2,stroke:#0d47a1,stroke-width:3px,color:#fff
      style H fill:#0d7f1f,stroke:#0d4f1f,stroke-width:3px,color:#fff
      style I fill:#e65100,stroke:#bf360c,stroke-width:3px,color:#fff
      style J fill:#1976d2,stroke:#0d47a1,stroke-width:3px,color:#fff
```

## Deployment Mode Detection

The handler automatically detects the deployment mode using environment variables:

| Environment | RUNPOD_POD_ID | FLASH_* vars | Mode Detected |
|-------------|---------------|--------------|---------------|
| Local dev | ❌ Not set | ❌ Not set | Live Serverless only |
| Live Serverless | ✅ Set | ❌ Not set | Live Serverless |
| Flash Mothership | ✅ Set | ✅ FLASH_IS_MOTHERSHIP=true | Flash Deployed |
| Flash Child | ✅ Set | ✅ FLASH_MOTHERSHIP_ID, FLASH_RESOURCE_NAME | Flash Deployed |

Flash-specific environment variables:
- `FLASH_IS_MOTHERSHIP=true` - Set for mothership endpoints
- `FLASH_MOTHERSHIP_ID` - Set for child endpoints
- `FLASH_RESOURCE_NAME` - Specifies resource config name

## Request Format Differences

### Live Serverless Request
```json
{
  "function_name": "my_function",
  "function_code": "def my_function(): return 'result'",
  "args": [],
  "kwargs": {},
  "dependencies": ["requests"]
}
```

### Flash Deployed Request
```json
{
  "function_name": "my_function",
  "args": [],
  "kwargs": {}
}
```

Note: Flash requests omit `function_code` because code is pre-deployed.

## Shared Protocol

Both modes use identical serialization:
- **Arguments**: cloudpickle + base64 encoding
- **Results**: cloudpickle + base64 encoding
- **Deserialization**: Same SerializationUtils for both paths

## Key Files

- `src/handler.py` - RunPod Serverless handler
- `src/lb_handler.py` - Load Balancer (HTTP) handler
- `src/remote_executor.py` - Unified execution orchestrator with mode detection
- `src/unpack_volume.py` - Flash artifact extraction from shadow volumes
- `/app/flash_manifest.json` - Function registry for Flash deployments (created by flash build)