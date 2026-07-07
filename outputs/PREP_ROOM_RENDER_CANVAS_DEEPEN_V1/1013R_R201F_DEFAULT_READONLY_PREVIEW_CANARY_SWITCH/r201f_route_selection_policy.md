# R201F Route Selection Policy

| Request | Canary Flag | Selected Engine |
| --- | --- | --- |
| no `preview_engine` / `auto` | off | legacy |
| no `preview_engine` / `auto` | on | lean |
| `preview_engine=legacy` | on or off | legacy |
| `preview_engine=lean` | on or off | lean, unless lean fails and fallback is required |

The route remains `/api/prep-room/uploaded-lesson-entry-preview`. R201F does not delete the legacy path.
