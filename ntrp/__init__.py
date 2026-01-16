import litellm

__version__ = "0.1.0"


# some global settings to make life easier lol
litellm.drop_params = True
litellm.suppress_debug_info = True

# lunary hooks
litellm.success_callback = ["lunary"]
litellm.failure_callback = ["lunary"]
