import litellm

__version__ = "0.1.0"


# some global settings to make life easier lol
litellm.drop_params = True
litellm.suppress_debug_info = True

# langfuse hooks (OTEL integration for langfuse v3)
litellm.success_callback = ["langfuse_otel"]
litellm.failure_callback = ["langfuse_otel"]
