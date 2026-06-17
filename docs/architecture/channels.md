# Channel Adapter Boundary

Channels own delivery concerns. Runtime owns execution concerns.

Channel-owned fields:
- native thread IDs
- native message IDs
- delivery queues
- continuation tokens
- approval/auth/final-response rendering

Runtime-owned fields:
- session IDs
- run IDs
- turn IDs
- step IDs
- event cursors
- workflow state

`continuation_token` is a channel resume handle, not a durable runtime queue. Adapters must serialize delivery per native thread before entering the runtime.
