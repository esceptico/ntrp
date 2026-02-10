import asyncio

from evals.run import main

# Disable tracing callbacks for eval runs — must happen AFTER ntrp import
# (which sets them in ntrp/__init__.py) to prevent OTEL exporter threads
# from hanging the process when the Langfuse account is over quota.
import litellm

litellm.success_callback = []
litellm.failure_callback = []

asyncio.run(main())
